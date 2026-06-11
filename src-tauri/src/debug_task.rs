//! Runtime ownership for a one-shot debug run.

use std::sync::{
    Mutex,
    atomic::{AtomicU64, Ordering},
};

use tauri::async_runtime::JoinHandle;
use tokio_util::sync::CancellationToken;

use crate::error::{AppError, AppResult};

pub struct DebugTaskReservation {
    id: u64,
    cancel: CancellationToken,
}

impl DebugTaskReservation {
    pub fn id(&self) -> u64 {
        self.id
    }

    pub fn cancel_token(&self) -> CancellationToken {
        self.cancel.clone()
    }
}

pub struct DebugTaskHandle {
    id: u64,
    cancel: CancellationToken,
    join: Option<JoinHandle<()>>,
}

impl DebugTaskHandle {
    pub fn new(id: u64, cancel: CancellationToken, join: JoinHandle<()>) -> Self {
        Self {
            id,
            cancel,
            join: Some(join),
        }
    }

    fn pending(id: u64, cancel: CancellationToken) -> Self {
        Self {
            id,
            cancel,
            join: None,
        }
    }

    fn id(&self) -> u64 {
        self.id
    }

    pub fn cancel(&self) {
        self.cancel.cancel();
    }

    pub fn abort(&self) {
        if let Some(join) = &self.join {
            join.abort();
        }
    }

    pub async fn shutdown(mut self) {
        self.cancel.cancel();
        let Some(mut join) = self.join.take() else {
            return;
        };

        tokio::select! {
            result = &mut join => {
                if let Err(error) = result {
                    tracing::warn!(error = %error, "debug task finished with join error");
                }
            }
            () = tokio::time::sleep(std::time::Duration::from_secs(3)) => {
                tracing::warn!("debug task did not stop within timeout; aborting");
                join.abort();
            }
        }
    }

    pub fn is_running(&self) -> bool {
        if self.cancel.is_cancelled() {
            return false;
        }
        if let Some(join) = &self.join {
            return !join.inner().is_finished();
        }
        true
    }
}

pub struct DebugTaskRegistry {
    task: Mutex<Option<DebugTaskHandle>>,
    generation: AtomicU64,
}

impl Default for DebugTaskRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl DebugTaskRegistry {
    pub fn new() -> Self {
        Self {
            task: Mutex::new(None),
            generation: AtomicU64::new(0),
        }
    }

    pub fn is_running(&self) -> AppResult<bool> {
        let guard = self.task.lock().map_err(debug_lock_error)?;
        Ok(task_is_running(guard.as_ref()))
    }

    pub fn reserve(&self) -> AppResult<DebugTaskReservation> {
        let id = self.generation.fetch_add(1, Ordering::Relaxed) + 1;
        let cancel = CancellationToken::new();
        let mut guard = self.task.lock().map_err(debug_lock_error)?;
        if task_is_running(guard.as_ref()) {
            return Err(AppError::Engine("debug run already running".into()));
        }
        *guard = Some(DebugTaskHandle::pending(id, cancel.clone()));
        Ok(DebugTaskReservation { id, cancel })
    }

    pub fn cancel_reservation(&self, reservation: &DebugTaskReservation) -> AppResult<()> {
        let mut guard = self.task.lock().map_err(debug_lock_error)?;
        if guard
            .as_ref()
            .is_some_and(|task| task.id() == reservation.id())
        {
            if let Some(task) = guard.take() {
                task.cancel();
            }
        }
        reservation.cancel.cancel();
        Ok(())
    }

    pub fn install(
        &self,
        reservation: &DebugTaskReservation,
        task: DebugTaskHandle,
    ) -> AppResult<bool> {
        let mut guard = self.task.lock().map_err(debug_lock_error)?;
        if guard
            .as_ref()
            .is_some_and(|current| current.id() == reservation.id())
        {
            *guard = Some(task);
            Ok(true)
        } else {
            task.cancel();
            task.abort();
            Ok(false)
        }
    }

    pub fn take(&self) -> AppResult<Option<DebugTaskHandle>> {
        let mut guard = self.task.lock().map_err(debug_lock_error)?;
        Ok(guard.take())
    }

    pub fn clear_if_current(&self, id: u64) -> AppResult<()> {
        let mut guard = self.task.lock().map_err(debug_lock_error)?;
        if guard.as_ref().is_some_and(|task| task.id() == id) {
            *guard = None;
        }
        Ok(())
    }
}

fn task_is_running(task: Option<&DebugTaskHandle>) -> bool {
    task.is_some_and(DebugTaskHandle::is_running)
}

fn debug_lock_error(error: impl std::fmt::Display) -> AppError {
    AppError::Engine(format!("debug task state lock failed: {error}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn running_debug_task_blocks_reserve() {
        let registry = DebugTaskRegistry::new();
        let first = registry.reserve().unwrap();
        assert!(registry.reserve().is_err());
        registry.cancel_reservation(&first).unwrap();
    }
}
