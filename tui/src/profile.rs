//! Opt-in release-binary telemetry. Disabled runs perform no trace I/O.
use std::{io::{self, Write}, sync::{Arc, atomic::{AtomicU64, Ordering}}, time::{Instant, SystemTime, UNIX_EPOCH}};
#[derive(Clone)]
pub struct CountWriter(pub Arc<AtomicU64>);
impl Write for CountWriter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        let n = io::stdout().write(bytes)?;
        self.0.fetch_add(n as u64, Ordering::Relaxed);
        Ok(n)
    }
    fn flush(&mut self) -> io::Result<()> { io::stdout().flush() }
}
pub fn micros() -> u128 { SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_micros() }
pub struct Profile { path: Option<String>, rows: Vec<serde_json::Value>, pub events: u64, pub pending: usize }
impl Profile {
    pub fn new() -> Self { Self { path: std::env::var("OSRS_TERM_TRACE").ok(), rows: vec![], events: 0, pending: 0 } }
    pub fn frame(&mut self, start: Instant, bytes: u64, pos: Option<(u16,u16)>, drag: bool) {
        if self.path.is_some() { self.rows.push(serde_json::json!({"us":micros(),"draw_us":start.elapsed().as_micros(),"bytes":bytes,"events":self.events,"batch":self.pending,"pos":pos,"drag":drag})); }
        self.pending = 0;
    }
}
impl Drop for Profile { fn drop(&mut self) { if let Some(path) = &self.path { if let Ok(file) = std::fs::File::create(path) { let mut out = io::BufWriter::new(file); for row in &self.rows { let _ = writeln!(out,"{row}"); } } } } }
