//! Event-driven clean-detection seam for the freshness tracker.
//!
//! Linux inotify is drained synchronously at the request boundary. Other
//! platforms deliberately retain the authoritative stat differ until they can
//! provide the same completed-write guarantee.

#[cfg(target_os = "linux")]
mod platform {
    use inotify::{EventMask, Inotify, WatchMask};
    use std::path::PathBuf;

    const WATCH_MASK: WatchMask = WatchMask::MODIFY
        .union(WatchMask::CLOSE_WRITE)
        .union(WatchMask::CREATE)
        .union(WatchMask::DELETE)
        .union(WatchMask::MOVED_FROM)
        .union(WatchMask::MOVED_TO)
        .union(WatchMask::ATTRIB)
        .union(WatchMask::DELETE_SELF)
        .union(WatchMask::MOVE_SELF);

    pub struct Watch {
        root: PathBuf,
        inotify: Inotify,
        buffer: Vec<u8>,
        epoch: u64,
    }

    impl Watch {
        pub fn new(root: &str) -> Option<Self> {
            let root = std::fs::canonicalize(root).ok()?;
            let inotify = Inotify::init().ok()?;
            let mut watch = Self {
                root,
                inotify,
                buffer: vec![0; 64 * 1024],
                epoch: 0,
            };
            watch.install_all().then_some(watch)
        }

        pub fn rebuild(&mut self) -> bool {
            let Ok(inotify) = Inotify::init() else {
                return false;
            };
            self.inotify = inotify;
            self.install_all()
        }

        fn install_all(&mut self) -> bool {
            let mut directories = vec![self.root.clone()];
            let mut cursor = 0;
            while cursor < directories.len() {
                let directory = directories[cursor].clone();
                cursor += 1;
                if self.inotify.watches().add(&directory, WATCH_MASK).is_err() {
                    return false;
                }
                let Ok(entries) = std::fs::read_dir(&directory) else {
                    return false;
                };
                for entry in entries {
                    let Ok(entry) = entry else {
                        return false;
                    };
                    let Some(name) = entry.file_name().to_str().map(str::to_owned) else {
                        continue;
                    };
                    if name.starts_with('.') {
                        continue;
                    }
                    let Ok(kind) = entry.file_type() else {
                        continue;
                    };
                    if kind.is_dir() && !kind.is_symlink() {
                        directories.push(entry.path());
                    }
                }
            }
            true
        }

        pub fn checkpoint(&mut self) -> Option<u64> {
            let mut dirty = false;
            loop {
                let events = match self.inotify.read_events(&mut self.buffer) {
                    Ok(events) => events,
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => break,
                    Err(_) => return None,
                };
                let mut count = 0;
                for event in events {
                    count += 1;
                    dirty = true;
                    if event.mask.contains(EventMask::Q_OVERFLOW) {
                        // Overflow is still just dirty: rebuilding before the
                        // stat scan restores a complete watch set.
                        dirty = true;
                    }
                }
                if count == 0 {
                    break;
                }
            }
            if dirty {
                self.epoch = self.epoch.wrapping_add(1);
            }
            Some(self.epoch)
        }
    }
}

pub struct EventWatch {
    #[cfg(target_os = "linux")]
    inner: Option<platform::Watch>,
    seen: u64,
}

impl EventWatch {
    pub fn new(root: &str, enabled: bool) -> Self {
        #[cfg(not(target_os = "linux"))]
        let _ = (root, enabled);
        Self {
            #[cfg(target_os = "linux")]
            inner: enabled.then(|| platform::Watch::new(root)).flatten(),
            seen: 0,
        }
    }

    pub fn mode(&self) -> &'static str {
        #[cfg(target_os = "linux")]
        if self.inner.is_some() {
            return "inotify";
        }
        "stat"
    }

    pub fn is_clean(&mut self) -> bool {
        self.checkpoint()
            .is_some_and(|checkpoint| checkpoint == self.seen)
    }

    /// Rebuild the directory watch set before an authoritative scan. The scan
    /// covers the replacement gap; the post-scan checkpoint covers mutations
    /// that race with the scan itself.
    pub fn prepare_scan(&mut self) {
        #[cfg(target_os = "linux")]
        if self.inner.as_mut().is_some_and(|inner| !inner.rebuild()) {
            self.inner = None;
        }
    }

    pub fn checkpoint(&mut self) -> Option<u64> {
        #[cfg(target_os = "linux")]
        {
            let checkpoint = self.inner.as_mut()?.checkpoint();
            if checkpoint.is_none() {
                self.inner = None;
            }
            checkpoint
        }
        #[cfg(not(target_os = "linux"))]
        {
            None
        }
    }

    pub fn acknowledge_if_stable(&mut self, before: u64) -> bool {
        let Some(after) = self.checkpoint() else {
            return true;
        };
        if after != before {
            return false;
        }
        self.seen = after;
        true
    }
}
