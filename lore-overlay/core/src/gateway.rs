use crate::error::CaptureError;

/// A drafted artifact: a human title plus the Markdown body — the sections under
/// the type's headings, **without** frontmatter (`rac new` owns the frontmatter
/// and mints the id).
#[derive(Clone, Debug)]
pub struct DraftedArtifact {
    pub title: String,
    pub body: String,
}

/// The model seam. The interview/draft step runs in the host behind a
/// bring-your-own gateway (ADR-002/035/067: AI lives in the host, never the
/// engine). It is a trait so the core is testable without a real model.
pub trait Gateway {
    /// Draft an artifact of `artifact_type` from the author's raw `intent`,
    /// shaped by the real `schema_json` (so it uses only the schema's sections).
    fn draft(
        &self,
        artifact_type: &str,
        schema_json: &str,
        intent: &str,
    ) -> Result<DraftedArtifact, CaptureError>;
}

/// Real OpenAI-compatible gateway client (LiteLLM / OpenRouter / Azure / Ollama /
/// vLLM …). Compiled only for the desktop app, behind the `net` feature.
#[cfg(feature = "net")]
pub struct OpenAiGateway {
    base_url: String,
    api_key: String,
    model: String,
    client: reqwest::blocking::Client,
}

#[cfg(feature = "net")]
impl OpenAiGateway {
    pub fn new(cfg: &crate::config::GatewayConfig) -> Self {
        Self {
            base_url: cfg.base_url.trim_end_matches('/').to_string(),
            api_key: cfg.api_key.clone(),
            model: cfg.model.clone(),
            client: reqwest::blocking::Client::new(),
        }
    }
}

#[cfg(feature = "net")]
impl Gateway for OpenAiGateway {
    fn draft(
        &self,
        artifact_type: &str,
        schema_json: &str,
        intent: &str,
    ) -> Result<DraftedArtifact, CaptureError> {
        let system = format!(
            "You draft a Lore (requirements-as-code) {ty} artifact from the author's words. \
             Use ONLY the section headings the schema lists; never invent sections, and never \
             emit frontmatter. Capture only what the author says — where a required section has \
             no material, write a one-line 'TODO: (gap to confirm)'. Respond with STRICT JSON: \
             {{\"title\": <string>, \"body\": <markdown string of the sections>}}. \
             Schema: {schema}",
            ty = artifact_type,
            schema = schema_json
        );
        let payload = serde_json::json!({
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": intent},
            ],
        });
        let resp = self
            .client
            .post(format!("{}/chat/completions", self.base_url))
            .bearer_auth(&self.api_key)
            .json(&payload)
            .send()
            .map_err(|e| CaptureError::Gateway(e.to_string()))?;
        if !resp.status().is_success() {
            return Err(CaptureError::Gateway(format!("HTTP {}", resp.status())));
        }
        let v: serde_json::Value = resp
            .json()
            .map_err(|e| CaptureError::Gateway(e.to_string()))?;
        let content = v["choices"][0]["message"]["content"]
            .as_str()
            .ok_or_else(|| CaptureError::Gateway("no content in gateway response".into()))?;
        let parsed: serde_json::Value = serde_json::from_str(content)
            .map_err(|e| CaptureError::Gateway(format!("model did not return JSON: {e}")))?;
        let title = parsed["title"].as_str().unwrap_or("").trim().to_string();
        let body = parsed["body"].as_str().unwrap_or("").to_string();
        if title.is_empty() || body.is_empty() {
            return Err(CaptureError::Gateway(
                "model returned an empty title or body".into(),
            ));
        }
        Ok(DraftedArtifact { title, body })
    }
}
