use std::fmt;

/// One error type for the whole capture flow, naming which seam failed.
#[derive(Debug)]
pub enum CaptureError {
    /// The `rac` engine seam (schema / new / validate) failed.
    Rac(String),
    /// The model gateway seam failed.
    Gateway(String),
    /// The git/GitHub publish seam failed.
    Publish(String),
    /// A local filesystem operation failed.
    Io(String),
    /// Output from a subprocess could not be parsed (e.g. the minted id).
    Parse(String),
}

impl fmt::Display for CaptureError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CaptureError::Rac(m) => write!(f, "rac error: {m}"),
            CaptureError::Gateway(m) => write!(f, "gateway error: {m}"),
            CaptureError::Publish(m) => write!(f, "publish error: {m}"),
            CaptureError::Io(m) => write!(f, "io error: {m}"),
            CaptureError::Parse(m) => write!(f, "parse error: {m}"),
        }
    }
}

impl std::error::Error for CaptureError {}

impl From<std::io::Error> for CaptureError {
    fn from(e: std::io::Error) -> Self {
        CaptureError::Io(e.to_string())
    }
}
