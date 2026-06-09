//! enigo 键盘模拟封装
//! enigo 键盘模拟实现

use crate::engine::skill_attempt::KeySender as KeySenderTrait;
use enigo::{Enigo, Key, Keyboard, Settings};

/// 基于 enigo 的真实键盘发送器
pub struct EnigoKeySender {
    enigo: Enigo,
}

impl EnigoKeySender {
    pub fn new() -> Result<Self, String> {
        let enigo =
            Enigo::new(&Settings::default()).map_err(|e| format!("enigo 初始化失败: {e}"))?;
        tracing::info!("EnigoKeySender 已初始化");
        Ok(Self { enigo })
    }
}

impl KeySenderTrait for EnigoKeySender {
    fn send_key(&mut self, key: &str) -> bool {
        let k = match parse_key(key) {
            Some(k) => k,
            None => {
                tracing::warn!("无法解析按键: {key}");
                return false;
            }
        };
        // 按下
        if self.enigo.key(k, enigo::Direction::Press).is_err() {
            tracing::warn!("enigo 按键失败(press): {key}");
            return false;
        }
        // 弹起
        std::thread::sleep(std::time::Duration::from_millis(20));
        if self.enigo.key(k, enigo::Direction::Release).is_err() {
            tracing::warn!("enigo 按键失败(release): {key}");
            return false;
        }
        true
    }
}

/// 将字符串按键名映射为 enigo::Key
fn parse_key(key: &str) -> Option<Key> {
    let k = key.trim().to_lowercase();
    match k.as_str() {
        // 字母
        "a" => Some(Key::A),
        "b" => Some(Key::B),
        "c" => Some(Key::C),
        "d" => Some(Key::D),
        "e" => Some(Key::E),
        "f" => Some(Key::F),
        "g" => Some(Key::G),
        "h" => Some(Key::H),
        "i" => Some(Key::I),
        "j" => Some(Key::J),
        "k" => Some(Key::K),
        "l" => Some(Key::L),
        "m" => Some(Key::M),
        "n" => Some(Key::N),
        "o" => Some(Key::O),
        "p" => Some(Key::P),
        "q" => Some(Key::Q),
        "r" => Some(Key::R),
        "s" => Some(Key::S),
        "t" => Some(Key::T),
        "u" => Some(Key::U),
        "v" => Some(Key::V),
        "w" => Some(Key::W),
        "x" => Some(Key::X),
        "y" => Some(Key::Y),
        "z" => Some(Key::Z),

        // 数字
        "0" => Some(Key::Num0),
        "1" => Some(Key::Num1),
        "2" => Some(Key::Num2),
        "3" => Some(Key::Num3),
        "4" => Some(Key::Num4),
        "5" => Some(Key::Num5),
        "6" => Some(Key::Num6),
        "7" => Some(Key::Num7),
        "8" => Some(Key::Num8),
        "9" => Some(Key::Num9),

        // F 键
        "f1" => Some(Key::F1),
        "f2" => Some(Key::F2),
        "f3" => Some(Key::F3),
        "f4" => Some(Key::F4),
        "f5" => Some(Key::F5),
        "f6" => Some(Key::F6),
        "f7" => Some(Key::F7),
        "f8" => Some(Key::F8),
        "f9" => Some(Key::F9),
        "f10" => Some(Key::F10),
        "f11" => Some(Key::F11),
        "f12" => Some(Key::F12),

        // 功能键
        "space" => Some(Key::Space),
        "enter" | "return" => Some(Key::Return),
        "tab" => Some(Key::Tab),
        "esc" | "escape" => Some(Key::Escape),
        "backspace" => Some(Key::Backspace),
        "delete" => Some(Key::Delete),
        "insert" => Some(Key::Insert),
        "home" => Some(Key::Home),
        "end" => Some(Key::End),
        "pageup" => Some(Key::PageUp),
        "pagedown" => Some(Key::PageDown),
        "up" => Some(Key::UpArrow),
        "down" => Some(Key::DownArrow),
        "left" => Some(Key::LeftArrow),
        "right" => Some(Key::RightArrow),

        _ => {
            let chars: Vec<char> = k.chars().collect();
            if chars.len() == 1 {
                Some(Key::Unicode(chars[0]))
            } else {
                None
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_key_letters() {
        assert_eq!(parse_key("a"), Some(Key::A));
        assert_eq!(parse_key("Z"), Some(Key::Z));
        assert_eq!(parse_key("f1"), Some(Key::F1));
        assert_eq!(parse_key("F12"), Some(Key::F12));
    }

    #[test]
    fn test_parse_key_numbers() {
        assert_eq!(parse_key("1"), Some(Key::Num1));
        assert_eq!(parse_key("9"), Some(Key::Num9));
    }

    #[test]
    fn test_parse_key_special() {
        assert_eq!(parse_key("space"), Some(Key::Space));
        assert_eq!(parse_key("enter"), Some(Key::Return));
        assert_eq!(parse_key("up"), Some(Key::UpArrow));
    }

    #[test]
    fn test_parse_key_unknown() {
        assert_eq!(parse_key("nonexistent_key_xyz"), None);
    }
}
