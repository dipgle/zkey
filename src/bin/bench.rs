// SPDX-License-Identifier: AGPL-3.0-or-later
use std::time::Instant;
use zkey_core::telex::compose;

fn main() {
    let words = ["dduwowngf", "tieengs", "nguyeenx", "NGUYEENX", "thuwowngr"];
    let mut samples = Vec::with_capacity(100_000);
    for word in words {
        for _ in 0..1000 {
            std::hint::black_box(compose(word, true));
        }
    }
    for i in 0..100_000 {
        let word = words[i % words.len()];
        let prefix = &word[..1 + i % word.len()];
        let start = Instant::now();
        std::hint::black_box(compose(std::hint::black_box(prefix), true));
        samples.push(start.elapsed().as_nanos());
    }
    samples.sort_unstable();
    println!(
        "core replay only; samples={}; p50={}ns p95={}ns p99={}ns max={}ns",
        samples.len(),
        samples[50_000],
        samples[95_000],
        samples[99_000],
        samples[99_999]
    );
    println!("Not keyboard-to-screen latency; no IBus/compositor/application in this measurement.");
}
