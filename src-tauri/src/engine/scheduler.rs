//! 最小调度器
//!
//! CycleExecutor 内部调度器实现
//!
//! CycleExecutor 模式下的调度器非常简单:
//! - 只有一个"当前活跃轨道"（当前 Phase 按 priority 排序后的 slot 队列）
//! - tick() 返回是否执行了技能
//! - 引擎层负责 sleep 和重调度

/// 调度项
#[derive(Debug, Clone)]
pub struct ScheduleItem {
    pub skill_id: String,
    pub priority: u32,
    pub due_ms: u64,
}

/// 简单调度器 — 按 priority 排序
#[derive(Debug, Default)]
pub struct Scheduler {
    pub queue: Vec<ScheduleItem>,
}

impl Scheduler {
    pub fn new() -> Self {
        Self { queue: Vec::new() }
    }

    /// 添加调度项
    pub fn push(&mut self, skill_id: &str, priority: u32, due_ms: u64) {
        self.queue.push(ScheduleItem {
            skill_id: skill_id.into(),
            priority,
            due_ms,
        });
    }

    /// 选择下一个到期的项（按 due_ms, then priority）
    pub fn choose_next(&self, now_ms: u64) -> Option<&ScheduleItem> {
        self.queue
            .iter()
            .filter(|item| item.due_ms <= now_ms)
            .min_by_key(|item| (item.due_ms, item.priority))
    }

    /// 清空队列
    pub fn clear(&mut self) {
        self.queue.clear();
    }

    /// 移除指定技能
    pub fn remove(&mut self, skill_id: &str) {
        self.queue.retain(|item| item.skill_id != skill_id);
    }

    pub fn is_empty(&self) -> bool {
        self.queue.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_choose_next_by_priority() {
        let mut s = Scheduler::new();
        s.push("skB", 2, 0);
        s.push("skA", 1, 0);
        let next = s.choose_next(0).unwrap();
        assert_eq!(next.skill_id, "skA"); // priority 1 < 2
    }

    #[test]
    fn test_choose_next_by_due() {
        let mut s = Scheduler::new();
        s.push("skB", 1, 100);
        s.push("skA", 2, 0);
        let next = s.choose_next(50).unwrap();
        assert_eq!(next.skill_id, "skA"); // due_ms 0 < 100, even though skA has lower priority
    }

    #[test]
    fn test_not_due_yet() {
        let mut s = Scheduler::new();
        s.push("skA", 1, 100);
        assert!(s.choose_next(50).is_none());
    }

    #[test]
    fn test_remove() {
        let mut s = Scheduler::new();
        s.push("skA", 1, 0);
        s.push("skB", 2, 0);
        s.remove("skA");
        let next = s.choose_next(0).unwrap();
        assert_eq!(next.skill_id, "skB");
    }
}
