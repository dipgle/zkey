// SPDX-License-Identifier: AGPL-3.0-or-later
//! Embed the REAL native build-input SHA-256; no external Rust build crates.
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
    process::{Command, Stdio},
};
fn walk(directory: &Path, paths: &mut Vec<PathBuf>) {
    for entry in fs::read_dir(directory).expect("read native source directory") {
        let path = entry.expect("read native source entry").path();
        if path.is_dir() {
            walk(&path, paths);
        } else if path.is_file() {
            paths.push(path);
        }
    }
}
fn main() {
    let root =
        PathBuf::from(std::env::var_os("CARGO_MANIFEST_DIR").expect("native manifest directory"));
    let mut paths = vec![
        root.join("Cargo.toml"),
        root.join("Cargo.lock"),
        root.join("build.rs"),
    ];
    walk(&root.join("src"), &mut paths);
    paths.sort();
    println!("cargo:rerun-if-changed=src");
    let mut child = Command::new("sha256sum")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("system sha256sum is required to attest native build inputs");
    {
        let mut input = child.stdin.take().expect("hash stdin");
        for path in paths {
            let relative = path
                .strip_prefix(&root)
                .expect("source stays within native tree")
                .to_str()
                .expect("native source path is UTF-8");
            println!("cargo:rerun-if-changed={relative}");
            let data = fs::read(&path).expect("read native build input");
            input
                .write_all(&(relative.len() as u64).to_le_bytes())
                .expect("hash path length");
            input
                .write_all(relative.as_bytes())
                .expect("hash relative path");
            input
                .write_all(&(data.len() as u64).to_le_bytes())
                .expect("hash source length");
            input.write_all(&data).expect("hash source bytes");
        }
    }
    let result = child.wait_with_output().expect("wait for source SHA-256");
    assert!(result.status.success(), "native source attestation failed");
    let output = String::from_utf8(result.stdout).expect("SHA-256 output is UTF-8");
    let hash = output
        .split_whitespace()
        .next()
        .expect("SHA-256 output exists");
    assert!(
        hash.len() == 64 && hash.bytes().all(|b| b.is_ascii_hexdigit()),
        "invalid source SHA-256 output"
    );
    println!("cargo:rustc-env=ZKEY_NATIVE_SOURCE_SHA256={hash}");
    let bridge = PathBuf::from(std::env::var_os("OUT_DIR").expect("native build output"))
        .join("libzkey_webkit_bridge.so");
    let rustc = std::env::var_os("RUSTC").expect("Cargo rustc executable");
    let status = Command::new(rustc)
        .args([
            "--edition=2024",
            "--crate-name=zkey_webkit_bridge",
            "--crate-type=cdylib",
            "-Dwarnings",
            "-Copt-level=2",
            "-Clto=fat",
            "-Cstrip=symbols",
            "-Ccodegen-units=1",
        ])
        .arg(root.join("src/webkit_bridge.rs"))
        .arg("-o")
        .arg(&bridge)
        .status()
        .expect("compile the process-local WebKit bridge");
    assert!(
        status.success(),
        "process-local WebKit bridge compilation failed"
    );
}
