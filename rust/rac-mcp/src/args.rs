//! Lenient tool-argument handling — an emulation of the oracle's
//! FastMCP/pydantic 2.13 validation layer (PORT-CONTRACT.d/10 §5).
//!
//! Landmines reproduced:
//! - Unknown extra arguments are silently ignored (pydantic model default).
//! - Lax coercion: a numeric string is accepted for `int` (`depth:"2"` → 2),
//!   an integral float too; `bool` accepts 0/1 and the usual string forms.
//! - A failed validation returns the pydantic error text VERBATIM, including
//!   the pydantic major.minor (`2.13`) in the docs URL — pinned constants of
//!   this contract, tied to the oracle's pydantic version.

use serde_json::Value;

/// Pinned: the oracle bundles pydantic 2.13 (the URL embeds major.minor).
const PYDANTIC_VERSION: &str = "2.13";

#[derive(Clone, Copy)]
pub enum Kind {
    Str,
    OptStr,
    OptListStr,
    Int,
    Bool,
}

pub struct Param {
    pub name: &'static str,
    pub kind: Kind,
    pub required: bool,
}

/// A coerced argument value.
pub enum Arg {
    Str(String),
    OptStr(Option<String>),
    OptListStr(Option<Vec<String>>),
    Int(i64),
    Bool(bool),
    /// Parameter absent and not required — the tool body applies its default.
    Missing,
}

struct FieldError {
    loc: String,
    msg: String,
    err_type: &'static str,
    input_repr: String,
    input_type: &'static str,
}

/// Python `repr` of a JSON value as pydantic renders `input_value`.
pub fn py_repr(v: &Value) -> String {
    match v {
        Value::Null => "None".to_string(),
        Value::Bool(true) => "True".to_string(),
        Value::Bool(false) => "False".to_string(),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                i.to_string()
            } else if let Some(u) = n.as_u64() {
                u.to_string()
            } else {
                rac_engine::pycompat::py_float_repr(n.as_f64().unwrap_or(0.0))
            }
        }
        Value::String(s) => rac_engine::pycompat::py_repr_str(s),
        Value::Array(items) => {
            let parts: Vec<String> = items.iter().map(py_repr).collect();
            format!("[{}]", parts.join(", "))
        }
        Value::Object(map) => {
            let parts: Vec<String> = map
                .iter()
                .map(|(k, v)| format!("{}: {}", rac_engine::pycompat::py_repr_str(k), py_repr(v)))
                .collect();
            format!("{{{}}}", parts.join(", "))
        }
    }
}

/// The Python type name pydantic reports as `input_type`.
fn py_type_name(v: &Value) -> &'static str {
    match v {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(n) => {
            if n.is_f64() {
                "float"
            } else {
                "int"
            }
        }
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

fn coerce(param: &Param, value: &Value) -> Result<Arg, FieldError> {
    let err = |msg: &str, t: &'static str| FieldError {
        loc: param.name.to_string(),
        msg: msg.to_string(),
        err_type: t,
        input_repr: py_repr(value),
        input_type: py_type_name(value),
    };
    match param.kind {
        Kind::Str => match value {
            Value::String(s) => Ok(Arg::Str(s.clone())),
            _ => Err(err("Input should be a valid string", "string_type")),
        },
        Kind::OptStr => match value {
            Value::Null => Ok(Arg::OptStr(None)),
            Value::String(s) => Ok(Arg::OptStr(Some(s.clone()))),
            _ => Err(err("Input should be a valid string", "string_type")),
        },
        Kind::OptListStr => match value {
            Value::Null => Ok(Arg::OptListStr(None)),
            Value::Array(items) => {
                let mut out = Vec::with_capacity(items.len());
                for item in items {
                    match item {
                        Value::String(s) => out.push(s.clone()),
                        _ => return Err(err("Input should be a valid string", "string_type")),
                    }
                }
                Ok(Arg::OptListStr(Some(out)))
            }
            _ => Err(err("Input should be a valid list", "list_type")),
        },
        Kind::Int => match value {
            Value::Number(n) => {
                if let Some(i) = n.as_i64() {
                    Ok(Arg::Int(i))
                } else if let Some(f) = n.as_f64() {
                    if f.fract() == 0.0 && f.is_finite() {
                        Ok(Arg::Int(f as i64))
                    } else {
                        Err(err(
                            "Input should be a valid integer, got a number with a fractional part",
                            "int_from_float",
                        ))
                    }
                } else {
                    Err(err("Input should be a valid integer", "int_type"))
                }
            }
            Value::String(s) => match s.trim().parse::<i64>() {
                Ok(i) => Ok(Arg::Int(i)),
                Err(_) => Err(err(
                    "Input should be a valid integer, unable to parse string as an integer",
                    "int_parsing",
                )),
            },
            _ => Err(err("Input should be a valid integer", "int_type")),
        },
        Kind::Bool => match value {
            Value::Bool(b) => Ok(Arg::Bool(*b)),
            Value::Number(n) => match n.as_f64() {
                Some(0.0) => Ok(Arg::Bool(false)),
                Some(1.0) => Ok(Arg::Bool(true)),
                _ => Err(err(
                    "Input should be a valid boolean, unable to interpret input",
                    "bool_parsing",
                )),
            },
            Value::String(s) => {
                let lower = s.trim().to_lowercase();
                match lower.as_str() {
                    "true" | "t" | "yes" | "y" | "on" | "1" => Ok(Arg::Bool(true)),
                    "false" | "f" | "no" | "n" | "off" | "0" => Ok(Arg::Bool(false)),
                    _ => Err(err(
                        "Input should be a valid boolean, unable to interpret input",
                        "bool_parsing",
                    )),
                }
            }
            _ => Err(err("Input should be a valid boolean", "bool_type")),
        },
    }
}

/// Validate `arguments` against `params`, returning coerced values in
/// parameter order — or the verbatim pydantic error text (the `isError:true`
/// content) on failure. `title` is the pydantic model title, which leaks the
/// *Python handler* name (`find_decisions_toolArguments`,
/// `retrieve_grounding_toolArguments`) — hard-coded per tool by the caller.
pub fn validate(
    tool: &str,
    title: &str,
    params: &[Param],
    arguments: &Value,
) -> Result<Vec<Arg>, String> {
    let empty = serde_json::Map::new();
    let map = arguments.as_object().unwrap_or(&empty);
    let mut out: Vec<Arg> = Vec::with_capacity(params.len());
    let mut errors: Vec<FieldError> = Vec::new();
    for param in params {
        match map.get(param.name) {
            None => {
                if param.required {
                    errors.push(FieldError {
                        loc: param.name.to_string(),
                        msg: "Field required".to_string(),
                        err_type: "missing",
                        input_repr: py_repr(arguments),
                        input_type: "dict",
                    });
                } else {
                    out.push(Arg::Missing);
                }
            }
            Some(value) => match coerce(param, value) {
                Ok(arg) => out.push(arg),
                Err(e) => errors.push(e),
            },
        }
    }
    if errors.is_empty() {
        return Ok(out);
    }
    let plural = if errors.len() == 1 { "" } else { "s" };
    let mut text = format!(
        "Error executing tool {tool}: {} validation error{plural} for {title}",
        errors.len()
    );
    for e in &errors {
        text.push_str(&format!(
            "\n{}\n  {} [type={}, input_value={}, input_type={}]\n    For further information visit https://errors.pydantic.dev/{}/v/{}",
            e.loc, e.msg, e.err_type, e.input_repr, e.input_type, PYDANTIC_VERSION, e.err_type
        ));
    }
    Err(text)
}
