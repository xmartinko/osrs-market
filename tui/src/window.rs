use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct Bounds {
    pub x: u16,
    pub y: u16,
    pub w: u16,
    pub h: u16,
}
impl Bounds {
    pub fn contains(self, x: u16, y: u16) -> bool {
        x >= self.x
            && y >= self.y
            && x < self.x.saturating_add(self.w)
            && y < self.y.saturating_add(self.h)
    }
}
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Hit {
    Close,
    Resize,
    Title,
    Body,
}

pub fn hit(rect: Bounds, x: u16, y: u16) -> Option<Hit> {
    if !rect.contains(x, y) {
        return None;
    }
    if y == rect.y && x == rect.x + rect.w.saturating_sub(3) {
        return Some(Hit::Close);
    }
    if x >= rect.x + rect.w.saturating_sub(2) && y >= rect.y + rect.h.saturating_sub(2) {
        return Some(Hit::Resize);
    }
    Some(if y == rect.y { Hit::Title } else { Hit::Body })
}
pub fn topmost(rects: &[Bounds], x: u16, y: u16) -> Option<usize> {
    rects.iter().rposition(|r| r.contains(x, y))
}
pub fn clamp(mut rect: Bounds, width: u16, height: u16) -> Bounds {
    rect.w = rect.w.max(28).min(width);
    rect.h = rect.h.max(8).min(height);
    rect.x = rect.x.min(width.saturating_sub(rect.w));
    rect.y = rect.y.min(height.saturating_sub(rect.h));
    rect
}
pub fn translate(rect: Bounds, dx: i32, dy: i32, width: u16, height: u16) -> Bounds {
    clamp(
        Bounds {
            x: (rect.x as i32 + dx).clamp(0, u16::MAX as i32) as u16,
            y: (rect.y as i32 + dy).clamp(0, u16::MAX as i32) as u16,
            ..rect
        },
        width,
        height,
    )
}
pub fn resize(rect: Bounds, dx: i32, dy: i32, width: u16, height: u16) -> Bounds {
    let w = (rect.w as i32 + dx).clamp(28, u16::MAX as i32) as u16;
    let h = (rect.h as i32 + dy).clamp(8, u16::MAX as i32) as u16;
    clamp(
        Bounds {
            w: w.min(width.saturating_sub(rect.x)),
            h: h.min(height.saturating_sub(rect.y)),
            ..rect
        },
        width,
        height,
    )
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Window {
    pub view: String,
    #[serde(default)]
    pub id: u64,
    #[serde(default = "default_item")]
    pub item: u64,
    #[serde(default)]
    pub link: String,
    #[serde(default)]
    pub options: serde_json::Value,
    pub rect: Bounds,
    #[serde(default)]
    pub scroll: usize,
    #[serde(default)]
    pub filter: String,
    #[serde(default)]
    pub sort: u8,
}

#[cfg(test)]
pub fn fuzzy(query: &str, candidate: &str) -> bool {
    let mut chars = candidate.chars().flat_map(char::to_lowercase);
    query
        .chars()
        .flat_map(char::to_lowercase)
        .all(|c| chars.by_ref().any(|v| v == c))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn r() -> Bounds {
        Bounds {
            x: 10,
            y: 5,
            w: 50,
            h: 20,
        }
    }
    #[test]
    fn hit_regions() {
        assert_eq!(hit(r(), 57, 5), Some(Hit::Close));
        assert_eq!(hit(r(), 59, 24), Some(Hit::Resize));
        assert_eq!(hit(r(), 20, 5), Some(Hit::Title));
        assert_eq!(hit(r(), 20, 6), Some(Hit::Body));
        assert_eq!(hit(r(), 60, 10), None);
        assert_eq!(hit(r(), 10, 25), None);
    }
    #[test]
    fn overlapping_z_order() {
        assert_eq!(topmost(&[r(), r()], 20, 8), Some(1));
        assert_eq!(topmost(&[r()], 0, 0), None);
    }
    #[test]
    fn drag_clamps_all_edges() {
        assert_eq!(
            translate(r(), -100, -100, 80, 30),
            Bounds { x: 0, y: 0, ..r() }
        );
        let v = translate(r(), 10000, 10000, 80, 30);
        assert_eq!((v.x, v.y), (30, 10));
    }
    #[test]
    fn resizing_and_tiny_terminal() {
        let v = resize(r(), -100, -100, 80, 30);
        assert_eq!((v.w, v.h), (28, 8));
        let v = resize(r(), 100, 100, 80, 30);
        assert_eq!((v.x, v.y, v.w, v.h), (10, 5, 70, 25));
        assert_eq!(
            clamp(r(), 2, 1),
            Bounds {
                x: 0,
                y: 0,
                w: 2,
                h: 1
            }
        );
        assert_eq!(clamp(r(), 0, 0), Bounds::default());
    }
    #[test]
    fn fuzzy_subsequence() {
        assert!(fuzzy("mkt", "Market table"));
        assert!(!fuzzy("zz", "Market table"));
    }
}

pub fn chart_index(x: u16, left: u16, width: u16, count: usize) -> usize {
    if width == 0 || count == 0 {
        return 0;
    }
    ((x.saturating_sub(left) as usize * count) / width as usize).min(count - 1)
}
#[cfg(test)]
mod chart_tests {
    use super::*;
    #[test]
    fn hover_clamps_to_bucket() {
        assert_eq!(chart_index(0, 10, 100, 80), 0);
        assert_eq!(chart_index(60, 10, 100, 80), 40);
        assert_eq!(chart_index(110, 10, 100, 80), 79);
        assert_eq!(chart_index(10, 10, 0, 0), 0);
    }
}

fn default_item() -> u64 {
    855
}
impl Window {
    pub fn option(&self, key: &str, fallback: &str) -> String {
        self.options[key].as_str().unwrap_or(fallback).to_string()
    }
    pub fn flag(&self, key: &str, fallback: bool) -> bool {
        self.options[key].as_bool().unwrap_or(fallback)
    }
    pub fn set(&mut self, key: &str, value: impl Into<serde_json::Value>) {
        if !self.options.is_object() {
            self.options = serde_json::json!({});
        }
        self.options[key] = value.into();
    }
}

pub fn edge(rect: Bounds, dx: i32, dy: i32, width: u16, height: u16, grow: bool) -> Bounds {
    let mut r = rect;
    if grow {
        if dx < 0 {
            r.w = r.w.saturating_add(r.x);
            r.x = 0;
        }
        if dx > 0 {
            r.w = width.saturating_sub(r.x);
        }
        if dy < 0 {
            r.h = r.h.saturating_add(r.y);
            r.y = 0;
        }
        if dy > 0 {
            r.h = height.saturating_sub(r.y);
        }
    } else {
        if dx < 0 {
            r.x = 0;
        }
        if dx > 0 {
            r.x = width.saturating_sub(r.w);
        }
        if dy < 0 {
            r.y = 0;
        }
        if dy > 0 {
            r.y = height.saturating_sub(r.h);
        }
    }
    clamp(r, width, height)
}
#[cfg(test)]
mod edge_tests {
    use super::*;
    #[test]
    fn snap_and_resize_edges() {
        let r = Bounds {
            x: 10,
            y: 5,
            w: 30,
            h: 10,
        };
        assert_eq!(edge(r, 1, 0, 100, 40, false).x, 70);
        assert_eq!(edge(r, 0, 1, 100, 40, false).y, 30);
        let v = edge(r, -1, 0, 100, 40, true);
        assert_eq!((v.x, v.w), (0, 40));
        assert_eq!(edge(r, 0, 1, 100, 40, true).h, 35);
        assert_eq!(
            edge(r, 1, 0, 2, 1, true),
            Bounds {
                x: 0,
                y: 0,
                w: 2,
                h: 1
            }
        );
    }
}

/// Missing, corrupt, and explicitly empty layouts all restore to an empty workspace.
pub fn decode_layout(bytes: Option<&[u8]>) -> Vec<Window> {
    bytes
        .and_then(|v| serde_json::from_slice(v).ok())
        .unwrap_or_default()
}
pub fn clear_workspace(windows: &mut Vec<Window>, closed: &mut Vec<Vec<Window>>) {
    if !windows.is_empty() {
        closed.push(std::mem::take(windows));
    }
}
#[cfg(test)]
mod workspace_tests {
    use super::*;
    #[test]
    fn launch_and_clear_restore_exact_windows() {
        assert!(decode_layout(None).is_empty());
        assert!(decode_layout(Some(b"garbage")).is_empty());
        assert!(decode_layout(Some(b"[]")).is_empty());
        let mut windows = vec![
            Window {
                view: "QM".into(),
                item: 4151,
                link: "red".into(),
                ..Window::default()
            },
            Window {
                view: "Candlestick chart".into(),
                item: 11802,
                link: "blue".into(),
                ..Window::default()
            },
        ];
        let bytes = serde_json::to_vec(&windows).unwrap();
        assert_eq!(decode_layout(Some(&bytes))[0].item, 4151);
        let mut closed = vec![];
        clear_workspace(&mut windows, &mut closed);
        assert!(windows.is_empty());
        clear_workspace(&mut windows, &mut closed);
        assert_eq!(closed.len(), 1);
        windows.extend(closed.pop().unwrap());
        assert_eq!(serde_json::to_vec(&windows).unwrap(), bytes);
    }
}
