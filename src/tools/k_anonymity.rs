use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Serialize, Deserialize)]
pub struct AnonymizedRecord {
    pub cohort_id: String,
    pub cohort_size: usize,
    pub data: HashMap<String, f64>,
}

pub struct KAnonymityEnforcer {
    min_k: usize,
}

impl KAnonymityEnforcer {
    pub fn new(min_k: usize) -> Self { Self { min_k } }

    pub fn enforce(&self, records: Vec<AnonymizedRecord>) -> Vec<AnonymizedRecord> {
        records.into_iter()
            .filter(|r| r.cohort_size >= self.min_k)
            .collect()
    }

    pub fn form_cohort(&self, records: Vec<HashMap<String, f64>>, key_fields: &[String]) -> Vec<AnonymizedRecord> {
        let mut groups: HashMap<String, Vec<HashMap<String, f64>>> = HashMap::new();
        for record in records {
            let key: String = key_fields.iter()
                .map(|f| record.get(f).map(|v| format!("{:.0}", v)).unwrap_or_default())
                .collect::<Vec<_>>()
                .join("|");
            groups.entry(key).or_default().push(record);
        }
        groups.into_iter()
            .filter(|(_, members)| members.len() >= self.min_k)
            .map(|(key, members)| {
                let mut avg_data = HashMap::new();
                if let Some(first) = members.first() {
                    for (k, v) in first {
                        let avg = members.iter().filter_map(|m| m.get(k)).sum::<f64>() / members.len() as f64;
                        avg_data.insert(k.clone(), avg);
                    }
                }
                AnonymizedRecord { cohort_id: key, cohort_size: members.len(), data: avg_data }
            })
            .collect()
    }
}
