//! A drag recomposes only the old/new window rectangles from a frozen scene.
//! No table sorting, chart preparation, HTTP, or file access on motion.
use super::*;
use ratatui::{backend::TestBackend, buffer::Buffer};
use std::cell::{Cell, RefCell};

pub struct Scene {
    base: Buffer,
    sprite: Buffer,
    composed: RefCell<Buffer>,
    previous: Cell<Rect>,
}
impl Scene {
    fn copy(source: &Buffer, src: Rect, dest: &mut Buffer, x: u16, y: u16) {
        for dy in 0..src.height {
            for dx in 0..src.width {
                if x + dx < dest.area.right() && y + dy < dest.area.bottom() {
                    dest[(x + dx, y + dy)] = source[(src.x + dx, src.y + dy)].clone();
                }
            }
        }
    }
    pub fn draw(&self, f: &mut Frame, rect: Rect) {
        let mut cells = self.composed.borrow_mut();
        let old = self.previous.get();
        Self::copy(&self.base, old, &mut cells, old.x, old.y);
        Self::copy(
            &self.sprite,
            Rect::new(
                0,
                0,
                rect.width.min(self.sprite.area.width),
                rect.height.min(self.sprite.area.height),
            ),
            &mut cells,
            rect.x,
            rect.y,
        );
        // Ratatui requires a complete frame; panel work is restricted to the dirty rectangles.
        f.buffer_mut().clone_from(&cells);
        if rect.width != self.sprite.area.width || rect.height != self.sprite.area.height {
            f.render_widget(
                Block::default()
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(ACCENT)),
                rect,
            );
        }
        self.previous.set(rect);
    }
}
impl App {
    pub fn cache_drag(&mut self) {
        if self
            .drag
            .as_ref()
            .is_none_or(|d| d.pan || d.resize.is_some())
            || self.drag_scene.is_some()
        {
            return;
        }
        let Some(w) = self.windows.last() else { return };
        let rect = Rect::new(w.rect.x, w.rect.y, w.rect.w, w.rect.h);
        let mut terminal = Terminal::new(TestBackend::new(self.width, self.height + 2)).unwrap();
        let full = terminal
            .draw(|f| self.draw_full(f, false))
            .unwrap()
            .buffer
            .clone();
        let base = terminal
            .draw(|f| self.draw_full(f, true))
            .unwrap()
            .buffer
            .clone();
        let mut sprite = Buffer::empty(Rect::new(0, 0, rect.width, rect.height));
        Scene::copy(&full, rect, &mut sprite, 0, 0);
        self.drag_scene = Some(Scene {
            base,
            sprite,
            composed: RefCell::new(full),
            previous: Cell::new(rect),
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cached_drag_matches_full_redraw_across_overlap() {
        let (tx, _) = mpsc::unbounded_channel();
        let mut app = App::new("http://test".into(), Some("Log console".into()), tx);
        app.clamp(150, 45);
        let mut below = app.windows[0].clone();
        below.id = 2;
        below.rect = Bounds {
            x: 0,
            y: 0,
            w: 100,
            h: 30,
        };
        app.windows.insert(0, below);
        app.windows[1].rect = Bounds {
            x: 8,
            y: 3,
            w: 100,
            h: 30,
        };
        app.drag = Some(Drag {
            rect: app.windows[1].rect,
            x: 10,
            y: 3,
            resize: None,
            pan: false,
            offset: 0,
        });
        app.cache_drag();
        let mut terminal = Terminal::new(TestBackend::new(150, 45)).unwrap();
        for (x, y) in [(20, 7), (0, 0), (40, 12)] {
            app.windows[1].rect = Bounds {
                x,
                y,
                w: 100,
                h: 30,
            };
            let cached = terminal.draw(|f| app.draw(f)).unwrap().buffer.clone();
            let full = terminal
                .draw(|f| app.draw_full(f, false))
                .unwrap()
                .buffer
                .clone();
            for row in 0..43 {
                for col in 0..150 {
                    assert_eq!(cached[(col, row)], full[(col, row)], "at {col},{row}");
                }
            }
        }
    }
}
