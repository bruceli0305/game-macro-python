//! Runtime ownership for the background engine task.

use std::sync::{
    Mutex,
    atomic::{AtomicU64, Ordering},
};

use tauri::async_runtime::JoinHandle;
use tokio_util::sync::CancellationToken;

use crate::error::{AppError, AppResult};

/// Reserved startup slot for a task that has not been spawned yet.
pub struct EngineTaskReservation {
    id: u64,
    cancel: CancellationToken,
}

impl EngineTaskReservation {
    pub fn id(&self) -> u64 {
        self.id
    }

    pub fn cancel_token(&self) -> CancellationToken {
        self.cancel.clone()
    }

    pub fn is_cancelled(&self) -> bool {
        self.cancel.is_cancelled()
    }
}

/// Runtime handle for the active engine task.
pub struct EngineTaskHandle {
    id: u64,
    cancel: CancellationToken,
    join: Option<JoinHandle<()>>,
}

impl EngineTaskHandle {
    /// Creates a task handle for a spawned engine loop.
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

    #[cfg(test)]
    pub(crate) fn for_test(id: u64, cancel: CancellationToken) -> Self {
        Self {
            id,
            cancel,
            join: None,
        }
    }

    fn id(&self) -> u64 {
        self.id
    }

    /// Requests cooperative shutdown.
    pub fn cancel(&self) {
        self.cancel.cancel();
    }

    pub fn abort(&self) {
        if let Some(join) = &self.join {
            join.abort();
        }
    }

    /// Requests shutdown and waits for the task to exit.
    pub async fn shutdown(mut self) {
        self.cancel.cancel();

        let Some(mut join) = self.join.take() else {
            return;
        };

        tokio::select! {
            result = &mut join => {
                if let Err(error) = result {
                    tracing::warn!(error = %error, "engine task finished with join error");
                }
            }
            () = tokio::time::sleep(std::time::Duration::from_secs(3)) => {
                tracing::warn!("engine task did not stop within timeout; aborting");
                join.abort();
            }
        }
    }

    /// Returns true when the cancellation token and join handle both look active.
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

/// Serializes engine start/stop ownership and protects pending startup windows.
pub struct EngineTaskRegistry {
    task: Mutex<Option<EngineTaskHandle>>,
    generation: AtomicU64,
}

impl Default for EngineTaskRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl EngineTaskRegistry {
    pub fn new() -> Self {
        Self {
            task: Mutex::new(None),
            generation: AtomicU64::new(0),
        }
    }

    pub fn is_running(&self) -> AppResult<bool> {
        let guard = self.task.lock().map_err(engine_lock_error)?;
        Ok(task_is_running(guard.as_ref()))
    }

    pub fn reserve(&self) -> AppResult<EngineTaskReservation> {
        let id = self.generation.fetch_add(1, Ordering::Relaxed) + 1;
        let cancel = CancellationToken::new();
        let mut guard = self.task.lock().map_err(engine_lock_error)?;
        if task_is_running(guard.as_ref()) {
            return Err(AppError::Engine("engine already running".into()));
        }
        *guard = Some(EngineTaskHandle::pending(id, cancel.clone()));
        Ok(EngineTaskReservation { id, cancel })
    }

    pub fn cancel_reservation(&self, reservation: &EngineTaskReservation) -> AppResult<()> {
        let mut guard = self.task.lock().map_err(engine_lock_error)?;
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
        reservation: &EngineTaskReservation,
        task: EngineTaskHandle,
    ) -> AppResult<bool> {
        let mut guard = self.task.lock().map_err(engine_lock_error)?;
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

    pub fn take(&self) -> AppResult<Option<EngineTaskHandle>> {
        let mut guard = self.task.lock().map_err(engine_lock_error)?;
        Ok(guard.take())
    }
}

fn task_is_running(task: Option<&EngineTaskHandle>) -> bool {
    task.is_some_and(EngineTaskHandle::is_running)
}

fn engine_lock_error(error: impl std::fmt::Display) -> AppError {
    AppError::Engine(format!("engine state lock failed: {error}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn running_token_blocks_reserve() {
        let registry = EngineTaskRegistry::new();
        let first = registry.reserve().unwrap();
        assert!(registry.reserve().is_err());
        registry.cancel_reservation(&first).unwrap();
    }

    #[test]
    fn cancelled_reservation_can_be_replaced() {
        let registry = EngineTaskRegistry::new();
        let first = registry.reserve().unwrap();
        registry.cancel_reservation(&first).unwrap();

        let second = registry.reserve().unwrap();
        assert!(registry.is_running().unwrap());
        registry.cancel_reservation(&second).unwrap();
    }

    #[test]
    fn stale_reservation_cannot_install_task() {
        let registry = EngineTaskRegistry::new();
        let reservation = registry.reserve().unwrap();
        registry.cancel_reservation(&reservation).unwrap();

        let task = EngineTaskHandle::for_test(reservation.id(), reservation.cancel_token());
        assert!(!registry.install(&reservation, task).unwrap());
        assert!(!registry.is_running().unwrap());
    }
}
