//! Durable identity for "this assistant message's usage has already been
//! added to the footer".
//!
//! The footer counters are a running total accumulated by the live
//! [`AgentEvent::MessageEnd`](rpi_harness::AgentEvent) handler. Run-end
//! reconciliation replaces that total with a rebuild from the durable session
//! log, and the two paths race: the `AgentEvent` broadcast is asynchronous, so a
//! `MessageEnd` that was already persisted can still be queued when
//! reconciliation runs. Adding it afterwards counts the same turn twice.
//!
//! Syncing the two paths with a barrier would need a watermark inside the drain
//! task; deduplicating by message identity instead keeps both call sites
//! independent and costs one comparison per event. `AssistantMessage` carries no
//! stable id of its own (providers may omit `response_id`), so the key is the
//! durable entry identity (`id` + `timestamp`, assigned by JSONL storage) plus
//! the token counts. That triple only collides when two distinct turns report
//! byte-identical identity and usage, which cannot happen within one run.

use rpi_ai::types::{AssistantMessage, Usage};

/// Identity of one assistant turn's usage as recorded in the session log.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub(super) struct Key {
    entry_id: u64,
    timestamp: i64,
    input: i64,
    output: i64,
    cache_read: i64,
    cache_write: i64,
}

impl Key {
    /// Build a key from the durable entry identity and the message's usage.
    pub(super) fn new(entry_id: u64, timestamp: i64, usage: &Usage) -> Self {
        Self {
            entry_id,
            timestamp,
            input: usage.input,
            output: usage.output,
            cache_read: usage.cache_read,
            cache_write: usage.cache_write,
        }
    }

    /// A message that arrived through the event broadcast has no entry id.
    /// Only its own fields are known, so match on the usage + timestamp half.
    /// `entry_id` stays 0 and [`super::TuiState::usage_was_counted`] compares
    /// the remaining fields.
    pub(super) fn from_message(message: &AssistantMessage) -> Self {
        Self::new(0, message.timestamp, &message.usage)
    }

    /// Whether `self` was produced by [`Key::from_message`] for the same turn
    /// that `recorded` (a reconciliation key) covers.
    pub(super) fn matches_recorded(&self, recorded: &Key) -> bool {
        self.timestamp == recorded.timestamp
            && self.input == recorded.input
            && self.output == recorded.output
            && self.cache_read == recorded.cache_read
            && self.cache_write == recorded.cache_write
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn usage(input: i64) -> Usage {
        Usage {
            input,
            output: 2,
            cache_read: 3,
            cache_write: 4,
            total_tokens: input + 9,
            ..Usage::zero()
        }
    }

    #[test]
    fn a_broadcast_key_matches_its_recorded_twin() {
        let recorded = Key::new(7, 1_000, &usage(10));
        let live = Key::from_message(&AssistantMessage {
            usage: usage(10),
            timestamp: 1_000,
            ..AssistantMessage::empty(rpi_ai::Api::AnthropicMessages, "p", "m", 0)
        });
        assert!(live.matches_recorded(&recorded));
    }

    /// The same timestamp with different token counts is a different turn: two
    /// turns of one run can land in the same millisecond on a fast provider.
    #[test]
    fn a_matching_timestamp_with_different_usage_does_not_match() {
        let recorded = Key::new(7, 1_000, &usage(10));
        let live = Key::from_message(&AssistantMessage {
            usage: usage(99),
            timestamp: 1_000,
            ..AssistantMessage::empty(rpi_ai::Api::AnthropicMessages, "p", "m", 0)
        });
        assert!(!live.matches_recorded(&recorded));
    }

    /// Neither half alone is enough: a later turn shares the token counts.
    #[test]
    fn matching_usage_in_a_later_millisecond_does_not_match() {
        let recorded = Key::new(7, 1_000, &usage(10));
        let live = Key::from_message(&AssistantMessage {
            usage: usage(10),
            timestamp: 2_000,
            ..AssistantMessage::empty(rpi_ai::Api::AnthropicMessages, "p", "m", 0)
        });
        assert!(!live.matches_recorded(&recorded));
    }
}
