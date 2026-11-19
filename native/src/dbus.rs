// SPDX-License-Identifier: AGPL-3.0-or-later
//! Minimal D-Bus client written on `std` only: wire marshalling, SASL EXTERNAL
//! authentication over a Unix socket, and a blocking message loop.
//!
//! Scope is what an input-method engine needs: little-endian messages, no file
//! descriptor passing, no GVariant text format. Every decoder is total: bad
//! input is an `Err`, never a panic (release builds abort on panic), and every
//! size is bounded. Contents of strings are never copied into error messages,
//! so a typed word cannot leak through a diagnostic.
use std::{
    collections::VecDeque,
    io::{Read, Write},
    os::linux::net::SocketAddrExt,
    os::unix::net::{SocketAddr, UnixStream},
    time::Duration,
};

/// Largest accepted message (header + body). The spec allows 128 MiB; an engine
/// never needs more than a surrounding-text snapshot.
pub const MAX_MESSAGE: usize = 4 << 20;
const MAX_HEADER_FIELDS: usize = 1 << 20;
const MAX_DEPTH: usize = 32;
const MAX_PENDING: usize = 1024;

pub const METHOD_CALL: u8 = 1;
pub const METHOD_RETURN: u8 = 2;
pub const ERROR: u8 = 3;
pub const SIGNAL: u8 = 4;

#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Byte(u8),
    Bool(bool),
    I32(i32),
    U32(u32),
    Str(String),
    Path(String),
    Sig(String),
    /// Element signature + items. The signature is explicit so empty arrays keep their type.
    Array(String, Vec<Value>),
    Struct(Vec<Value>),
    Dict(Box<Value>, Box<Value>),
    Variant(Box<Value>),
}

impl Value {
    pub fn signature(&self) -> String {
        match self {
            Value::Byte(_) => "y".into(),
            Value::Bool(_) => "b".into(),
            Value::I32(_) => "i".into(),
            Value::U32(_) => "u".into(),
            Value::Str(_) => "s".into(),
            Value::Path(_) => "o".into(),
            Value::Sig(_) => "g".into(),
            Value::Array(element, _) => format!("a{element}"),
            Value::Struct(items) => {
                format!(
                    "({})",
                    items.iter().map(Value::signature).collect::<String>()
                )
            }
            Value::Dict(key, value) => format!("{{{}{}}}", key.signature(), value.signature()),
            Value::Variant(_) => "v".into(),
        }
    }
    pub fn str(text: &str) -> Value {
        Value::Str(text.to_owned())
    }
    pub fn as_u32(&self) -> Result<u32, String> {
        match self {
            Value::U32(v) => Ok(*v),
            _ => Err("Expected uint32 D-Bus argument".into()),
        }
    }
    pub fn as_str(&self) -> Result<&str, String> {
        match self {
            Value::Str(v) | Value::Path(v) => Ok(v),
            _ => Err("Expected string D-Bus argument".into()),
        }
    }
    pub fn as_variant(&self) -> Result<&Value, String> {
        match self {
            Value::Variant(v) => Ok(v),
            _ => Err("Expected variant D-Bus argument".into()),
        }
    }
    pub fn as_struct(&self) -> Result<&[Value], String> {
        match self {
            Value::Struct(v) => Ok(v),
            _ => Err("Expected struct D-Bus argument".into()),
        }
    }
}

fn align_of(first: u8) -> usize {
    match first {
        b'y' | b'g' | b'v' => 1,
        b'b' | b'i' | b'u' | b's' | b'o' | b'a' => 4,
        _ => 8, // '(' and '{'
    }
}

fn pad(out: &mut Vec<u8>, alignment: usize) {
    while !out.len().is_multiple_of(alignment) {
        out.push(0);
    }
}

pub fn marshal(value: &Value, out: &mut Vec<u8>) -> Result<(), String> {
    marshal_at(value, out, 0)
}

fn marshal_text(text: &str, out: &mut Vec<u8>) -> Result<(), String> {
    if text.as_bytes().contains(&0) {
        return Err("D-Bus string contains NUL (contents omitted)".into());
    }
    let len = u32::try_from(text.len()).map_err(|_| "D-Bus string too long")?;
    pad(out, 4);
    out.extend_from_slice(&len.to_le_bytes());
    out.extend_from_slice(text.as_bytes());
    out.push(0);
    Ok(())
}

fn marshal_at(value: &Value, out: &mut Vec<u8>, depth: usize) -> Result<(), String> {
    if depth > MAX_DEPTH {
        return Err("D-Bus value nested too deeply".into());
    }
    match value {
        Value::Byte(v) => out.push(*v),
        Value::Bool(v) => {
            pad(out, 4);
            out.extend_from_slice(&u32::from(*v).to_le_bytes());
        }
        Value::I32(v) => {
            pad(out, 4);
            out.extend_from_slice(&v.to_le_bytes());
        }
        Value::U32(v) => {
            pad(out, 4);
            out.extend_from_slice(&v.to_le_bytes());
        }
        Value::Str(text) => marshal_text(text, out)?,
        Value::Path(text) => {
            if !valid_path(text) {
                return Err("Invalid D-Bus object path".into());
            }
            marshal_text(text, out)?;
        }
        Value::Sig(text) => marshal_signature(text, out)?,
        Value::Array(element, items) => {
            let first = *element.as_bytes().first().ok_or("Empty array signature")?;
            check_single_type(element)?;
            pad(out, 4);
            let length_at = out.len();
            out.extend_from_slice(&[0; 4]);
            pad(out, align_of(first));
            let start = out.len();
            for item in items {
                if item.signature() != *element {
                    return Err("Array element does not match its signature".into());
                }
                marshal_at(item, out, depth + 1)?;
            }
            let length = u32::try_from(out.len() - start).map_err(|_| "D-Bus array too long")?;
            if length as usize > MAX_MESSAGE {
                return Err("D-Bus array exceeds message bound".into());
            }
            out[length_at..length_at + 4].copy_from_slice(&length.to_le_bytes());
        }
        Value::Struct(items) => {
            if items.is_empty() {
                return Err("D-Bus struct cannot be empty".into());
            }
            pad(out, 8);
            for item in items {
                marshal_at(item, out, depth + 1)?;
            }
        }
        Value::Dict(key, entry) => {
            if !matches!(
                **key,
                Value::Byte(_)
                    | Value::Bool(_)
                    | Value::I32(_)
                    | Value::U32(_)
                    | Value::Str(_)
                    | Value::Path(_)
                    | Value::Sig(_)
            ) {
                return Err("D-Bus dict key must be a basic type".into());
            }
            pad(out, 8);
            marshal_at(key, out, depth + 1)?;
            marshal_at(entry, out, depth + 1)?;
        }
        Value::Variant(inner) => {
            marshal_signature(&inner.signature(), out)?;
            marshal_at(inner, out, depth + 1)?;
        }
    }
    Ok(())
}

fn marshal_signature(text: &str, out: &mut Vec<u8>) -> Result<(), String> {
    let len = u8::try_from(text.len()).map_err(|_| "D-Bus signature too long")?;
    out.push(len);
    out.extend_from_slice(text.as_bytes());
    out.push(0);
    Ok(())
}

pub fn valid_path(path: &str) -> bool {
    if path == "/" {
        return true;
    }
    path.starts_with('/')
        && !path.ends_with('/')
        && path[1..].split('/').all(|part| {
            !part.is_empty() && part.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
        })
}

/// Index just past the one complete type starting at `start`.
fn type_end(sig: &[u8], start: usize, depth: usize) -> Result<usize, String> {
    if depth > MAX_DEPTH {
        return Err("D-Bus signature nested too deeply".into());
    }
    match *sig.get(start).ok_or("Truncated D-Bus signature")? {
        b'y' | b'b' | b'i' | b'u' | b's' | b'o' | b'g' | b'v' => Ok(start + 1),
        b'a' => type_end(sig, start + 1, depth + 1),
        b'(' => {
            let mut at = start + 1;
            let mut members = 0;
            loop {
                if *sig.get(at).ok_or("Unterminated D-Bus struct signature")? == b')' {
                    return if members == 0 {
                        Err("Empty D-Bus struct signature".into())
                    } else {
                        Ok(at + 1)
                    };
                }
                at = type_end(sig, at, depth + 1)?;
                members += 1;
            }
        }
        b'{' => {
            let key = *sig.get(start + 1).ok_or("Truncated D-Bus dict signature")?;
            if !matches!(key, b'y' | b'b' | b'i' | b'u' | b's' | b'o' | b'g') {
                return Err("D-Bus dict key must be a basic type".into());
            }
            let value_end = type_end(sig, start + 2, depth + 1)?;
            if sig.get(value_end) != Some(&b'}') {
                return Err("Unterminated D-Bus dict signature".into());
            }
            Ok(value_end + 1)
        }
        _ => Err("Unsupported D-Bus type".into()),
    }
}

fn check_single_type(sig: &str) -> Result<(), String> {
    if type_end(sig.as_bytes(), 0, 0)? == sig.len() {
        Ok(())
    } else {
        Err("Expected exactly one complete D-Bus type".into())
    }
}

struct Reader<'a> {
    data: &'a [u8],
    off: usize,
}

impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8], String> {
        let end = self.off.checked_add(n).ok_or("D-Bus length overflow")?;
        let slice = self.data.get(self.off..end).ok_or("Truncated D-Bus data")?;
        self.off = end;
        Ok(slice)
    }
    fn align(&mut self, alignment: usize) -> Result<(), String> {
        let padding = (alignment - self.off % alignment) % alignment;
        self.take(padding).map(|_| ())
    }
    fn u32(&mut self) -> Result<u32, String> {
        self.align(4)?;
        let bytes = self.take(4)?;
        Ok(u32::from_le_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
    }
    fn text(&mut self, len: usize) -> Result<String, String> {
        let bytes = self.take(len)?;
        if self.take(1)?[0] != 0 {
            return Err("D-Bus string is not NUL-terminated".into());
        }
        let text = std::str::from_utf8(bytes).map_err(|_| "D-Bus string is not UTF-8")?;
        if text.contains('\0') {
            return Err("D-Bus string contains NUL".into());
        }
        Ok(text.to_owned())
    }
}

fn read_value(r: &mut Reader, sig: &[u8], start: usize, depth: usize) -> Result<Value, String> {
    if depth > MAX_DEPTH {
        return Err("D-Bus value nested too deeply".into());
    }
    match *sig.get(start).ok_or("Truncated D-Bus signature")? {
        b'y' => Ok(Value::Byte(r.take(1)?[0])),
        b'b' => match r.u32()? {
            0 => Ok(Value::Bool(false)),
            1 => Ok(Value::Bool(true)),
            _ => Err("Invalid D-Bus boolean".into()),
        },
        b'i' => Ok(Value::I32(r.u32()? as i32)),
        b'u' => Ok(Value::U32(r.u32()?)),
        b's' => {
            let len = r.u32()? as usize;
            Ok(Value::Str(r.text(len)?))
        }
        b'o' => {
            let len = r.u32()? as usize;
            let text = r.text(len)?;
            if !valid_path(&text) {
                return Err("Invalid D-Bus object path".into());
            }
            Ok(Value::Path(text))
        }
        b'g' => {
            let len = r.take(1)?[0] as usize;
            Ok(Value::Sig(r.text(len)?))
        }
        b'v' => {
            let len = r.take(1)?[0] as usize;
            let inner_sig = r.text(len)?;
            check_single_type(&inner_sig)?;
            let inner = read_value(r, inner_sig.as_bytes(), 0, depth + 1)?;
            Ok(Value::Variant(Box::new(inner)))
        }
        b'a' => {
            let len = r.u32()? as usize;
            if len > MAX_MESSAGE {
                return Err("D-Bus array exceeds message bound".into());
            }
            let element_end = type_end(sig, start + 1, depth + 1)?;
            let element = std::str::from_utf8(&sig[start + 1..element_end])
                .map_err(|_| "Non-UTF-8 signature")?
                .to_owned();
            r.align(align_of(sig[start + 1]))?;
            let stop = r.off.checked_add(len).ok_or("D-Bus length overflow")?;
            if stop > r.data.len() {
                return Err("Truncated D-Bus array".into());
            }
            let mut items = Vec::new();
            while r.off < stop {
                items.push(read_value(r, sig, start + 1, depth + 1)?);
            }
            if r.off != stop {
                return Err("D-Bus array length does not match its elements".into());
            }
            Ok(Value::Array(element, items))
        }
        b'(' => {
            r.align(8)?;
            let mut at = start + 1;
            let mut items = Vec::new();
            while *sig.get(at).ok_or("Unterminated D-Bus struct signature")? != b')' {
                items.push(read_value(r, sig, at, depth + 1)?);
                at = type_end(sig, at, depth + 1)?;
            }
            if items.is_empty() {
                return Err("Empty D-Bus struct".into());
            }
            Ok(Value::Struct(items))
        }
        b'{' => {
            r.align(8)?;
            let key = read_value(r, sig, start + 1, depth + 1)?;
            let entry = read_value(r, sig, start + 2, depth + 1)?;
            Ok(Value::Dict(Box::new(key), Box::new(entry)))
        }
        _ => Err("Unsupported D-Bus type".into()),
    }
}

/// Decode a body (or any value sequence) of the given signature.
pub fn unmarshal(sig: &str, data: &[u8]) -> Result<Vec<Value>, String> {
    let sig = sig.as_bytes();
    let mut r = Reader { data, off: 0 };
    let mut at = 0;
    let mut values = Vec::new();
    while at < sig.len() {
        values.push(read_value(&mut r, sig, at, 0)?);
        at = type_end(sig, at, 0)?;
    }
    if r.off != data.len() {
        return Err("Trailing bytes after D-Bus body".into());
    }
    Ok(values)
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Message {
    pub kind: u8,
    pub flags: u8,
    pub serial: u32,
    pub reply_serial: Option<u32>,
    pub path: Option<String>,
    pub interface: Option<String>,
    pub member: Option<String>,
    pub error_name: Option<String>,
    pub destination: Option<String>,
    pub sender: Option<String>,
    pub body: Vec<Value>,
}

impl Message {
    pub fn call(dest: &str, path: &str, interface: &str, member: &str, body: Vec<Value>) -> Self {
        Message {
            kind: METHOD_CALL,
            path: Some(path.into()),
            interface: Some(interface.into()),
            member: Some(member.into()),
            destination: Some(dest.into()),
            body,
            ..Default::default()
        }
    }
    pub fn signal(path: &str, interface: &str, member: &str, body: Vec<Value>) -> Self {
        Message {
            kind: SIGNAL,
            path: Some(path.into()),
            interface: Some(interface.into()),
            member: Some(member.into()),
            body,
            ..Default::default()
        }
    }
    pub fn encode(&self) -> Result<Vec<u8>, String> {
        let mut body = Vec::new();
        for value in &self.body {
            marshal(value, &mut body)?;
        }
        let signature: String = self.body.iter().map(Value::signature).collect();
        let mut fields = Vec::new();
        let mut field = |code: u8, value: Value| {
            fields.push(Value::Struct(vec![
                Value::Byte(code),
                Value::Variant(Box::new(value)),
            ]));
        };
        if let Some(v) = &self.path {
            field(1, Value::Path(v.clone()));
        }
        if let Some(v) = &self.interface {
            field(2, Value::Str(v.clone()));
        }
        if let Some(v) = &self.member {
            field(3, Value::Str(v.clone()));
        }
        if let Some(v) = &self.error_name {
            field(4, Value::Str(v.clone()));
        }
        if let Some(v) = self.reply_serial {
            field(5, Value::U32(v));
        }
        if let Some(v) = &self.destination {
            field(6, Value::Str(v.clone()));
        }
        if let Some(v) = &self.sender {
            field(7, Value::Str(v.clone()));
        }
        if !signature.is_empty() {
            field(8, Value::Sig(signature));
        }
        let mut out = vec![b'l', self.kind, self.flags, 1];
        out.extend_from_slice(
            &u32::try_from(body.len())
                .map_err(|_| "Body too long")?
                .to_le_bytes(),
        );
        out.extend_from_slice(&self.serial.to_le_bytes());
        marshal(&Value::Array("(yv)".into(), fields), &mut out)?;
        pad(&mut out, 8);
        out.extend_from_slice(&body);
        if out.len() > MAX_MESSAGE {
            return Err("D-Bus message exceeds size bound".into());
        }
        Ok(out)
    }
    /// Decode one complete message (header + body) from `data`.
    pub fn decode(data: &[u8]) -> Result<Self, String> {
        let header = data.get(..16).ok_or("Truncated D-Bus header")?;
        if header[0] != b'l' || header[3] != 1 {
            return Err("Unsupported D-Bus endianness or protocol version".into());
        }
        let body_len = u32::from_le_bytes([header[4], header[5], header[6], header[7]]) as usize;
        let fields_len =
            u32::from_le_bytes([header[12], header[13], header[14], header[15]]) as usize;
        let header_len = 16usize
            .checked_add(fields_len)
            .and_then(|n| n.checked_add(7))
            .map(|n| n & !7)
            .ok_or("D-Bus header length overflow")?;
        if fields_len > MAX_HEADER_FIELDS || header_len.checked_add(body_len) != Some(data.len()) {
            return Err("D-Bus message length mismatch".into());
        }
        // The fields array ends at 16 + fields_len; the rest up to header_len is padding.
        let fixed = unmarshal("yyyyuua(yv)", &data[..16 + fields_len])?;
        let mut message = Message {
            kind: match fixed[1] {
                Value::Byte(v) => v,
                _ => return Err("Malformed D-Bus header".into()),
            },
            flags: match fixed[2] {
                Value::Byte(v) => v,
                _ => return Err("Malformed D-Bus header".into()),
            },
            serial: fixed[5].as_u32()?,
            ..Default::default()
        };
        let mut signature = String::new();
        if let Value::Array(_, fields) = &fixed[6] {
            for field in fields {
                let parts = field.as_struct()?;
                let (Value::Byte(code), Value::Variant(value)) = (&parts[0], &parts[1]) else {
                    return Err("Malformed D-Bus header field".into());
                };
                let text = || value.as_str().map(str::to_owned);
                match code {
                    1 => message.path = Some(text()?),
                    2 => message.interface = Some(text()?),
                    3 => message.member = Some(text()?),
                    4 => message.error_name = Some(text()?),
                    5 => message.reply_serial = Some(value.as_u32()?),
                    6 => message.destination = Some(text()?),
                    7 => message.sender = Some(text()?),
                    8 => match &**value {
                        Value::Sig(s) => signature = s.clone(),
                        _ => return Err("Malformed D-Bus signature field".into()),
                    },
                    _ => {} // unknown fields must be ignored (spec)
                }
            }
        }
        // Body offsets are relative to a buffer that starts 8-aligned.
        message.body = unmarshal(&signature, &data[header_len..])?;
        match message.kind {
            METHOD_CALL if message.path.is_none() || message.member.is_none() => {
                Err("D-Bus method call without path/member".into())
            }
            SIGNAL
                if message.path.is_none()
                    || message.member.is_none()
                    || message.interface.is_none() =>
            {
                Err("D-Bus signal without path/interface/member".into())
            }
            METHOD_RETURN | ERROR if message.reply_serial.is_none() => {
                Err("D-Bus reply without reply serial".into())
            }
            _ => Ok(message),
        }
    }
}

fn unescape(text: &str) -> Result<Vec<u8>, String> {
    let bytes = text.as_bytes();
    let mut out = Vec::new();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' {
            let pair = bytes
                .get(i + 1..i + 3)
                .ok_or("Bad escape in D-Bus address")?;
            let value = std::str::from_utf8(pair)
                .ok()
                .and_then(|s| u8::from_str_radix(s, 16).ok())
                .ok_or("Bad escape in D-Bus address")?;
            out.push(value);
            i += 3;
        } else {
            out.push(bytes[i]);
            i += 1;
        }
    }
    Ok(out)
}

fn effective_uid() -> Result<String, String> {
    let status =
        std::fs::read_to_string("/proc/self/status").map_err(|_| "Cannot read process uid")?;
    status
        .lines()
        .find_map(|line| line.strip_prefix("Uid:"))
        .and_then(|rest| rest.split_whitespace().nth(1))
        .map(str::to_owned)
        .ok_or_else(|| "Cannot parse process uid".into())
}

pub struct Connection {
    stream: UnixStream,
    serial: u32,
    pending: VecDeque<Message>,
    pub unique_name: String,
}

impl Connection {
    /// Connect and authenticate only (no `Hello`): enough for a peer-to-peer test bus.
    pub fn open(address: &str) -> Result<Self, String> {
        let mut last = "No supported D-Bus address (only unix:path / unix:abstract)".to_owned();
        for candidate in address.split(';') {
            match Self::open_one(candidate) {
                Ok(connection) => return Ok(connection),
                Err(error) => last = error,
            }
        }
        Err(last)
    }
    fn open_one(address: &str) -> Result<Self, String> {
        let rest = address
            .strip_prefix("unix:")
            .ok_or("Unsupported D-Bus transport")?;
        let mut stream = None;
        for pair in rest.split(',') {
            match pair.split_once('=') {
                Some(("path", value)) => {
                    let path = unescape(value)?;
                    let path =
                        <std::ffi::OsString as std::os::unix::ffi::OsStringExt>::from_vec(path);
                    stream = Some(
                        UnixStream::connect(path).map_err(|_| "Cannot connect to D-Bus socket")?,
                    );
                }
                Some(("abstract", value)) => {
                    let name = unescape(value)?;
                    let socket = SocketAddr::from_abstract_name(&name)
                        .map_err(|_| "Bad abstract D-Bus address")?;
                    stream = Some(
                        UnixStream::connect_addr(&socket)
                            .map_err(|_| "Cannot connect to D-Bus socket")?,
                    );
                }
                _ => {}
            }
        }
        let mut stream = stream.ok_or("D-Bus address has no path or abstract part")?;
        let uid: String = effective_uid()?
            .bytes()
            .map(|b| format!("{b:02x}"))
            .collect();
        stream
            .write_all(format!("\0AUTH EXTERNAL {uid}\r\n").as_bytes())
            .map_err(|_| "Cannot send D-Bus authentication")?;
        let mut line = Vec::new();
        loop {
            let mut byte = [0u8; 1];
            stream
                .read_exact(&mut byte)
                .map_err(|_| "D-Bus authentication closed")?;
            line.push(byte[0]);
            if line.ends_with(b"\r\n") {
                break;
            }
            if line.len() > 512 {
                return Err("D-Bus authentication reply too long".into());
            }
        }
        if !line.starts_with(b"OK ") {
            return Err("D-Bus server rejected EXTERNAL authentication".into());
        }
        stream
            .write_all(b"BEGIN\r\n")
            .map_err(|_| "Cannot finish D-Bus authentication")?;
        Ok(Connection {
            stream,
            serial: 0,
            pending: VecDeque::new(),
            unique_name: String::new(),
        })
    }
    /// Connect to a message bus and register with `Hello`.
    pub fn connect(address: &str) -> Result<Self, String> {
        let mut connection = Self::open(address)?;
        let reply = connection.call(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "Hello",
            vec![],
        )?;
        connection.unique_name = reply
            .first()
            .ok_or("Empty Hello reply")?
            .as_str()?
            .to_owned();
        Ok(connection)
    }
    pub fn send(&mut self, message: &mut Message) -> Result<u32, String> {
        self.serial = self
            .serial
            .checked_add(1)
            .ok_or("D-Bus serial space exhausted")?;
        message.serial = self.serial;
        let bytes = message.encode()?;
        self.stream
            .write_all(&bytes)
            .map_err(|_| "Cannot write D-Bus message")?;
        Ok(self.serial)
    }
    fn read_message(&mut self) -> Result<Message, String> {
        let mut head = [0u8; 16];
        self.stream
            .read_exact(&mut head)
            .map_err(|_| "D-Bus connection closed")?;
        let body_len = u32::from_le_bytes([head[4], head[5], head[6], head[7]]) as usize;
        let fields_len = u32::from_le_bytes([head[12], head[13], head[14], head[15]]) as usize;
        let header_len = 16usize
            .checked_add(fields_len)
            .and_then(|n| n.checked_add(7))
            .map(|n| n & !7)
            .ok_or("D-Bus header length overflow")?;
        let total = header_len
            .checked_add(body_len)
            .ok_or("D-Bus length overflow")?;
        if fields_len > MAX_HEADER_FIELDS || total > MAX_MESSAGE {
            return Err("D-Bus message exceeds size bound".into());
        }
        let mut data = vec![0u8; total];
        data[..16].copy_from_slice(&head);
        self.stream
            .read_exact(&mut data[16..])
            .map_err(|_| "D-Bus connection closed mid-message")?;
        Message::decode(&data)
    }
    /// Next incoming message (queued ones first). Blocks.
    pub fn next_message(&mut self) -> Result<Message, String> {
        match self.pending.pop_front() {
            Some(message) => Ok(message),
            None => self.read_message(),
        }
    }
    /// Synchronous call. Unrelated messages that arrive meanwhile are kept for `next_message`.
    pub fn call(
        &mut self,
        dest: &str,
        path: &str,
        interface: &str,
        member: &str,
        body: Vec<Value>,
    ) -> Result<Vec<Value>, String> {
        let mut message = Message::call(dest, path, interface, member, body);
        let serial = self.send(&mut message)?;
        self.stream
            .set_read_timeout(Some(Duration::from_secs(5)))
            .map_err(|_| "Cannot set D-Bus timeout")?;
        let result = loop {
            let incoming = match self.read_message() {
                Ok(m) => m,
                Err(e) => break Err(e),
            };
            if incoming.reply_serial == Some(serial)
                && matches!(incoming.kind, METHOD_RETURN | ERROR)
            {
                break if incoming.kind == ERROR {
                    Err(format!(
                        "D-Bus error {}",
                        incoming.error_name.unwrap_or_default()
                    ))
                } else {
                    Ok(incoming.body)
                };
            }
            if self.pending.len() >= MAX_PENDING {
                break Err("Too many unrelated D-Bus messages while waiting for a reply".into());
            }
            self.pending.push_back(incoming);
        };
        let _ = self.stream.set_read_timeout(None);
        result
    }
    /// `RequestName` without queueing; Ok only when we became the primary owner.
    pub fn request_name(&mut self, name: &str) -> Result<(), String> {
        let reply = self.call(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "RequestName",
            vec![Value::str(name), Value::U32(4)],
        )?;
        match reply.first() {
            Some(Value::U32(1)) => Ok(()),
            _ => Err("D-Bus name is already owned".into()),
        }
    }
    pub fn reply(&mut self, call: &Message, body: Vec<Value>) -> Result<(), String> {
        if call.flags & 1 != 0 {
            return Ok(()); // NO_REPLY_EXPECTED
        }
        let mut message = Message {
            kind: METHOD_RETURN,
            reply_serial: Some(call.serial),
            destination: call.sender.clone(),
            body,
            ..Default::default()
        };
        self.send(&mut message).map(|_| ())
    }
    pub fn reply_error(&mut self, call: &Message, name: &str, text: &str) -> Result<(), String> {
        if call.flags & 1 != 0 {
            return Ok(());
        }
        let mut message = Message {
            kind: ERROR,
            reply_serial: Some(call.serial),
            error_name: Some(name.into()),
            destination: call.sender.clone(),
            body: vec![Value::str(text)],
            ..Default::default()
        };
        self.send(&mut message).map(|_| ())
    }
    pub fn emit(
        &mut self,
        path: &str,
        interface: &str,
        member: &str,
        body: Vec<Value>,
    ) -> Result<(), String> {
        let mut message = Message::signal(path, interface, member, body);
        self.send(&mut message).map(|_| ())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn round(value: Value) {
        let mut out = Vec::new();
        marshal(&value, &mut out).unwrap();
        let back = unmarshal(&value.signature(), &out).unwrap();
        assert_eq!(back, vec![value]);
    }

    #[test]
    fn every_type_roundtrips_with_correct_alignment() {
        round(Value::Byte(7));
        round(Value::Bool(true));
        round(Value::I32(-5));
        round(Value::U32(0xdead_beef));
        round(Value::str("tiếng 🙂"));
        round(Value::Path("/org/freedesktop/IBus".into()));
        round(Value::Sig("a{sv}".into()));
        round(Value::Array("u".into(), vec![Value::U32(1), Value::U32(2)]));
        round(Value::Array("{sv}".into(), vec![]));
        round(Value::Array(
            "{sv}".into(),
            vec![Value::Dict(
                Box::new(Value::str("k")),
                Box::new(Value::Variant(Box::new(Value::Bool(false)))),
            )],
        ));
        round(Value::Struct(vec![
            Value::Byte(1),
            Value::U32(2),
            Value::str("x"),
        ]));
        round(Value::Variant(Box::new(Value::Struct(vec![
            Value::str("a"),
            Value::Byte(9),
        ]))));
    }

    #[test]
    fn known_wire_bytes_match_the_specification() {
        let mut out = Vec::new();
        marshal(&Value::str("ab"), &mut out).unwrap();
        assert_eq!(out, [2, 0, 0, 0, b'a', b'b', 0]);
        // byte then uint32: three padding bytes before the u32.
        let mut out = vec![1];
        marshal(&Value::U32(0x0102_0304), &mut out).unwrap();
        assert_eq!(out, [1, 0, 0, 0, 4, 3, 2, 1]);
        // empty array of 8-aligned elements still pads to 8 after the length.
        let mut out = Vec::new();
        marshal(&Value::Array("(yv)".into(), vec![]), &mut out).unwrap();
        assert_eq!(out, [0, 0, 0, 0, 0, 0, 0, 0]);
        // variant carries its signature: "v" holding u32 5
        let mut out = Vec::new();
        marshal(&Value::Variant(Box::new(Value::U32(5))), &mut out).unwrap();
        assert_eq!(out, [1, b'u', 0, 0, 5, 0, 0, 0]);
    }

    #[test]
    fn message_roundtrips_and_header_is_eight_aligned() {
        let mut call = Message::call(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "RequestName",
            vec![Value::str("a.b"), Value::U32(4)],
        );
        call.serial = 9;
        let bytes = call.encode().unwrap();
        assert_eq!(&bytes[..4], [b'l', METHOD_CALL, 0, 1]);
        let back = Message::decode(&bytes).unwrap();
        assert_eq!(back, call);
        let body_start =
            bytes.len() - u32::from_le_bytes([bytes[4], bytes[5], bytes[6], bytes[7]]) as usize;
        assert_eq!(body_start % 8, 0);
    }

    #[test]
    fn ibus_text_has_the_signature_libibus_produces() {
        // Ground truth (IBus 1.5.34, python GI serialize_object): (sa{sv}sv)
        let text = Value::Variant(Box::new(Value::Struct(vec![
            Value::str("IBusText"),
            Value::Array("{sv}".into(), vec![]),
            Value::str("tiếng"),
            Value::Variant(Box::new(Value::Struct(vec![
                Value::str("IBusAttrList"),
                Value::Array("{sv}".into(), vec![]),
                Value::Array("v".into(), vec![]),
            ]))),
        ])));
        assert_eq!(text.as_variant().unwrap().signature(), "(sa{sv}sv)");
        round(text);
    }

    #[test]
    fn hostile_input_is_an_error_never_a_panic() {
        // Deterministic pseudo-random bytes through every decoder entry point.
        let mut seed = 0x9e37_79b9_7f4a_7c15u64;
        let mut next = || {
            seed ^= seed << 13;
            seed ^= seed >> 7;
            seed ^= seed << 17;
            seed
        };
        for round in 0..20_000 {
            let len = (next() % 96) as usize;
            let data: Vec<u8> = (0..len).map(|_| next() as u8).collect();
            let _ = Message::decode(&data);
            let _ = unmarshal("a(yv)", &data);
            let _ = unmarshal("a{sv}", &data);
            let _ = unmarshal("v", &data);
            let _ = unmarshal("(sa{sv}sv)", &data);
            if round % 4 == 0 {
                // A valid-looking header with a random tail.
                let mut framed = vec![b'l', 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0];
                framed.extend_from_slice(&data);
                let _ = Message::decode(&framed);
            }
        }
    }

    #[test]
    fn malformed_values_are_rejected_with_specific_errors() {
        assert!(unmarshal("s", &[3, 0, 0, 0, b'a', b'b', b'c', 1]).is_err()); // no NUL
        assert!(unmarshal("s", &[3, 0, 0, 0, b'a']).is_err()); // truncated
        assert!(unmarshal("b", &[2, 0, 0, 0]).is_err()); // not 0/1
        assert!(unmarshal("au", &[3, 0, 0, 0, 1, 2, 3]).is_err()); // length not a multiple of the element
        assert!(unmarshal("u", &[1, 0, 0, 0, 9]).is_err()); // trailing bytes
        assert!(unmarshal("a", &[]).is_err());
        assert!(unmarshal("()", &[]).is_err());
        assert!(unmarshal("{vs}", &[]).is_err()); // dict key must be basic
        assert!(marshal(&Value::str("a\0b"), &mut Vec::new()).is_err());
        assert!(marshal(&Value::Path("no-slash".into()), &mut Vec::new()).is_err());
        assert!(
            marshal(
                &Value::Array("u".into(), vec![Value::Byte(1)]),
                &mut Vec::new()
            )
            .is_err()
        );
        let mut deep = Value::U32(0);
        for _ in 0..100 {
            deep = Value::Variant(Box::new(deep));
        }
        assert!(marshal(&deep, &mut Vec::new()).is_err());
    }

    #[test]
    fn address_escapes_and_unsupported_transports_fail_cleanly() {
        assert_eq!(unescape("a%20b").unwrap(), b"a b");
        assert!(unescape("%2").is_err());
        assert!(unescape("%zz").is_err());
        assert!(Connection::open("tcp:host=localhost,port=1").is_err());
        assert!(Connection::open("unix:path=/nonexistent/zkey-test-socket").is_err());
    }
}
