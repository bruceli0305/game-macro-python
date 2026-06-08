/// 统一错误类型
use serde::Serialize;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum AppError {
    #[error("引擎错误: {0}")]
    Engine(String),

    #[error("截屏错误: {0}")]
    Capture(String),

    #[error("发键错误: {0}")]
    Input(String),

    #[error("配置错误: {0}")]
    Config(String),

    #[error("序列化错误: {0}")]
    Serialization(#[from] serde_json::Error),

    #[error("TOML serialize error: {0}")]
    TomlSerialize(#[from] toml::ser::Error),

    #[error("TOML deserialize error: {0}")]
    TomlDeserialize(#[from] toml::de::Error),

    #[error("IO 错误: {0}")]
    Io(#[from] std::io::Error),
}

impl AppError {
    pub fn code(&self) -> &'static str {
        match self {
            AppError::Engine(_) => "engine",
            AppError::Capture(_) => "capture",
            AppError::Input(_) => "input",
            AppError::Config(_) => "config",
            AppError::Serialization(_) => "serialization",
            AppError::TomlSerialize(_) => "toml_serialize",
            AppError::TomlDeserialize(_) => "toml_deserialize",
            AppError::Io(_) => "io",
        }
    }
}

pub type AppResult<T> = Result<T, AppError>;

#[derive(Debug, Clone, Serialize)]
pub struct CommandError {
    pub code: String,
    pub message: String,
}

impl From<AppError> for CommandError {
    fn from(value: AppError) -> Self {
        Self {
            code: value.code().into(),
            message: value.to_string(),
        }
    }
}

pub type CommandResult<T> = Result<T, CommandError>;
