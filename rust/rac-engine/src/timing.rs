//! Opt-in, stderr-only phase timing for performance diagnosis.
//!
//! `DECIDED_TIMING` is deliberately outside every output/parity contract. When it
//! is unset these helpers do not read clocks and emit nothing. Timing lines do
//! not contain paths, queries, identifiers, or document content.

use std::time::{Duration, Instant};

pub const ENV: &str = "DECIDED_TIMING";

pub fn enabled() -> bool {
    std::env::var_os(ENV).is_some()
}

/// Start an operation without touching the monotonic clock when timing is off.
pub fn start() -> Option<Instant> {
    enabled().then(Instant::now)
}

/// Emit one stable operation record. Counter names and order are caller-owned
/// constants; values are numeric so no corpus or query material can leak.
pub fn emit(operation: &'static str, duration: Duration, counters: &[(&'static str, u64)]) {
    if !enabled() {
        return;
    }
    eprint!(
        "decided-timing: op={operation} duration_ms={:.3}",
        duration.as_secs_f64() * 1000.0
    );
    for (name, value) in counters {
        eprint!(" {name}={value}");
    }
    eprintln!();
}

pub fn emit_since(
    operation: &'static str,
    started: Option<Instant>,
    counters: &[(&'static str, u64)],
) {
    if let Some(started) = started {
        emit(operation, started.elapsed(), counters);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn duration_conversion_is_fractional_milliseconds() {
        let duration = Duration::from_micros(1_234);
        assert_eq!(duration.as_secs_f64() * 1000.0, 1.234);
    }
}
