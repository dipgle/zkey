//! Stateless Telex replay. No I/O, keyboard hooks, clipboard or shared state.
pub mod telex;

/// Compose Telex (including previously composed Vietnamese after editing) into UTF-8.
/// Returns bytes written, -1 for insufficient capacity, -2 for invalid input.
/// `modern` selects hoà/thuý (1) versus hòa/thúy (0).
///
/// # Safety
/// Input must reference `len` readable bytes and output `capacity` writable bytes.
/// The buffers must not overlap. Null is permitted only with zero length/capacity.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn zkey_compose(
    input: *const u8,
    len: usize,
    output: *mut u8,
    capacity: usize,
    modern: bool,
) -> isize {
    if len > telex::MAX_KEYS * 4 || (len > 0 && input.is_null()) {
        return -2;
    }
    let bytes = if len == 0 {
        &[]
    } else {
        // SAFETY: the caller supplies a readable input slice, checked for null above.
        unsafe { std::slice::from_raw_parts(input, len) }
    };
    let Ok(raw) = std::str::from_utf8(bytes) else {
        return -2;
    };
    if raw.chars().count() > telex::MAX_KEYS
        || !raw
            .chars()
            .all(|c| c.is_ascii_alphabetic() || telex::is_vietnamese(c))
    {
        return -2;
    }
    let rendered = telex::compose(raw, modern);
    if rendered.len() > capacity {
        return -1;
    }
    if !rendered.is_empty() {
        if output.is_null() {
            return -2;
        }
        // SAFETY: caller supplies sufficient nonoverlapping writable storage.
        unsafe { std::ptr::copy_nonoverlapping(rendered.as_ptr(), output, rendered.len()) };
    }
    rendered.len() as isize
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ffi_boundaries() {
        let mut out = [0u8; 32];
        // SAFETY: all non-null pointers reference live buffers of the given sizes.
        unsafe {
            assert_eq!(
                zkey_compose(std::ptr::null(), 0, out.as_mut_ptr(), 32, true),
                0
            );
            assert_eq!(
                zkey_compose(std::ptr::null(), 1, out.as_mut_ptr(), 32, true),
                -2
            );
            assert_eq!(
                zkey_compose(b"a".as_ptr(), 1, std::ptr::null_mut(), 1, true),
                -2
            );
            assert_eq!(
                zkey_compose(b"as".as_ptr(), 2, out.as_mut_ptr(), 1, true),
                -1
            );
            assert_eq!(
                zkey_compose(b"a!".as_ptr(), 2, out.as_mut_ptr(), 32, true),
                -2
            );
            assert_eq!(
                zkey_compose(b"as".as_ptr(), 2, out.as_mut_ptr(), 32, true),
                2
            );
        }
        assert_eq!(&out[..2], "á".as_bytes());
    }
}
