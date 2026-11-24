// The tray's update item. One state behind one lock, so a check, a click and an install cannot disagree.
use std::time::{Duration, Instant};
use crate::shared::text;

pub const STARTUP_DELAY: Duration = Duration::from_secs(5);
pub const CHECK_INTERVAL: Duration = Duration::from_secs(6 * 60 * 60);
pub const MENU_COOLDOWN: Duration = Duration::from_secs(60);
pub const CHECK_TIMEOUT: Duration = Duration::from_secs(30);

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Phase {
    Idle,
    Checking,
    UpToDate,
    Failed,
    Available(String),
    Downloading(String),
    Installing(String),
    Unsupported,
}

impl Phase {
    fn labels(&self, current: &str) -> (String, String) {
        match self {
            Phase::Idle => ("업데이트 확인".into(), "Check for updates".into()),
            Phase::Checking => ("업데이트 확인 중...".into(), "Checking for updates...".into()),
            Phase::UpToDate => (format!("최신 버전 (v{current})"), format!("Up to date (v{current})")),
            Phase::Failed => (format!("업데이트 확인 실패 (v{current})"), format!("Update check failed (v{current})")),
            Phase::Available(next) => (format!("업데이트 하기 (v{next})"), format!("Update now (v{next})")),
            Phase::Downloading(next) => (format!("업데이트 다운로드 중 (v{next})"), format!("Downloading update (v{next})")),
            Phase::Installing(next) => (format!("업데이트 설치 중 (v{next})"), format!("Installing update (v{next})")),
            Phase::Unsupported => (format!("업데이트 미지원 (v{current})"), format!("Updates not supported (v{current})")),
        }
    }

    pub fn label(&self, current: &str) -> String {
        let (ko, en) = self.labels(current);
        text(&ko, &en)
    }

    pub fn clickable(&self) -> bool {
        matches!(self, Phase::Idle | Phase::Failed | Phase::Available(_))
    }

    // Only these may be replaced by an automatic check; the rest belong to something in progress.
    fn settled(&self) -> bool {
        matches!(self, Phase::Idle | Phase::UpToDate | Phase::Failed)
    }
}

#[derive(Debug, PartialEq, Eq)]
pub enum Outcome {
    Quiet,
    Found(String),
    CheckFailed(String),
}

pub struct Flow<T> {
    pub phase: Phase,
    pub pending: Option<T>,
    last_check: Option<Instant>,
    in_flight: bool,
    manual: bool,
}

impl<T: Clone> Flow<T> {
    pub fn new(phase: Phase) -> Self {
        Self { phase, pending: None, last_check: None, in_flight: false, manual: false }
    }

    // An automatic check keeps the current label until it has a result. True means start the request.
    pub fn begin_auto(&mut self, now: Instant, cooldown: Duration) -> bool {
        let rested = self.last_check.is_none_or(|last| now.duration_since(last) >= cooldown);
        if self.in_flight || !self.phase.settled() || !rested {
            return false;
        }
        self.in_flight = true;
        self.last_check = Some(now);
        true
    }

    // A click skips the cooldown. If a check is already running, the click takes over its result.
    pub fn begin_manual(&mut self, now: Instant) -> bool {
        if !matches!(self.phase, Phase::Idle | Phase::Failed) {
            return false;
        }
        self.phase = Phase::Checking;
        self.manual = true;
        self.last_check = Some(now);
        !std::mem::replace(&mut self.in_flight, true)
    }

    pub fn finish(&mut self, result: Result<Option<(String, T)>, String>) -> Outcome {
        self.in_flight = false;
        let manual = std::mem::take(&mut self.manual);
        if !self.phase.settled() && self.phase != Phase::Checking {
            return Outcome::Quiet;
        }
        match result {
            Ok(Some((version, update))) => {
                self.pending = Some(update);
                self.phase = Phase::Available(version.clone());
                Outcome::Found(version)
            }
            Ok(None) => {
                self.phase = Phase::UpToDate;
                Outcome::Quiet
            }
            Err(error) if manual => {
                self.phase = Phase::Failed;
                Outcome::CheckFailed(error)
            }
            Err(_) => Outcome::Quiet,
        }
    }

    pub fn begin_install(&mut self) -> Option<T> {
        let Phase::Available(version) = &self.phase else { return None; };
        let update = self.pending.clone()?;
        self.phase = Phase::Downloading(version.clone());
        Some(update)
    }

    pub fn downloaded(&mut self) {
        if let Phase::Downloading(version) = &self.phase {
            self.phase = Phase::Installing(version.clone());
        }
    }

    // The update is still there, so the same click can try again.
    pub fn install_failed(&mut self) {
        if let Phase::Downloading(version) | Phase::Installing(version) = &self.phase {
            self.phase = Phase::Available(version.clone());
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn flow(phase: Phase) -> Flow<u8> {
        Flow::new(phase)
    }

    fn found(version: &str) -> Result<Option<(String, u8)>, String> {
        Ok(Some((version.into(), 1)))
    }

    #[test]
    fn auto_check_runs_only_from_settled_states() {
        let now = Instant::now();
        for phase in [Phase::Idle, Phase::UpToDate, Phase::Failed] {
            assert!(flow(phase).begin_auto(now, MENU_COOLDOWN));
        }
        for phase in [Phase::Checking, Phase::Available("2".into()), Phase::Downloading("2".into()), Phase::Installing("2".into()), Phase::Unsupported] {
            assert!(!flow(phase).begin_auto(now, MENU_COOLDOWN));
        }
    }

    #[test]
    fn cooldown_blocks_auto_but_not_a_click() {
        let start = Instant::now();
        let mut state = flow(Phase::Idle);
        assert!(state.begin_auto(start, MENU_COOLDOWN));
        assert_eq!(state.finish(Err("offline".into())), Outcome::Quiet);
        assert!(!state.begin_auto(start + Duration::from_secs(59), MENU_COOLDOWN));
        assert!(state.begin_auto(start + MENU_COOLDOWN, MENU_COOLDOWN));
        state.finish(Err("offline".into()));
        assert!(state.begin_manual(start + MENU_COOLDOWN + Duration::from_secs(1)));
        assert_eq!(state.phase, Phase::Checking);
    }

    #[test]
    fn up_to_date_can_still_become_available() {
        let start = Instant::now();
        let mut state = flow(Phase::Idle);
        state.begin_auto(start, MENU_COOLDOWN);
        state.finish(Ok(None));
        assert_eq!(state.phase, Phase::UpToDate);
        assert!(!state.phase.clickable());
        assert!(state.begin_auto(start + MENU_COOLDOWN, MENU_COOLDOWN));
        assert_eq!(state.finish(found("2.0.0")), Outcome::Found("2.0.0".into()));
        assert_eq!(state.phase, Phase::Available("2.0.0".into()));
        assert!(state.pending.is_some());
    }

    #[test]
    fn automatic_failure_keeps_the_label_and_a_manual_one_reports() {
        let start = Instant::now();
        let mut state = flow(Phase::UpToDate);
        state.begin_auto(start, MENU_COOLDOWN);
        assert_eq!(state.finish(Err("offline".into())), Outcome::Quiet);
        assert_eq!(state.phase, Phase::UpToDate);

        let mut state = flow(Phase::Idle);
        assert!(state.begin_manual(start));
        assert_eq!(state.finish(Err("offline".into())), Outcome::CheckFailed("offline".into()));
        assert_eq!(state.phase, Phase::Failed);
        assert!(state.phase.clickable());
    }

    #[test]
    fn click_during_an_automatic_check_takes_over_its_result() {
        let start = Instant::now();
        let mut state = flow(Phase::Idle);
        assert!(state.begin_auto(start, MENU_COOLDOWN));
        assert!(!state.begin_manual(start));
        assert_eq!(state.phase, Phase::Checking);
        assert_eq!(state.finish(Err("offline".into())), Outcome::CheckFailed("offline".into()));
        assert_eq!(state.phase, Phase::Failed);
    }

    #[test]
    fn late_result_does_not_overwrite_an_install() {
        let mut state = flow(Phase::Downloading("2.0.0".into()));
        assert_eq!(state.finish(Ok(None)), Outcome::Quiet);
        assert_eq!(state.phase, Phase::Downloading("2.0.0".into()));
    }

    #[test]
    fn install_moves_through_phases_and_can_retry() {
        let mut state = flow(Phase::Idle);
        state.begin_manual(Instant::now());
        state.finish(found("2.0.0"));
        assert_eq!(state.begin_install(), Some(1));
        assert_eq!(state.phase, Phase::Downloading("2.0.0".into()));
        assert!(!state.phase.clickable());
        assert_eq!(state.begin_install(), None);
        state.downloaded();
        assert_eq!(state.phase, Phase::Installing("2.0.0".into()));
        state.install_failed();
        assert_eq!(state.phase, Phase::Available("2.0.0".into()));
        assert_eq!(state.begin_install(), Some(1));
    }

    #[test]
    fn labels_match_each_state() {
        let cases = [
            (Phase::Idle, "업데이트 확인", true),
            (Phase::Checking, "업데이트 확인 중...", false),
            (Phase::UpToDate, "최신 버전 (v1.0.0)", false),
            (Phase::Failed, "업데이트 확인 실패 (v1.0.0)", true),
            (Phase::Available("2.0.0".into()), "업데이트 하기 (v2.0.0)", true),
            (Phase::Downloading("2.0.0".into()), "업데이트 다운로드 중 (v2.0.0)", false),
            (Phase::Installing("2.0.0".into()), "업데이트 설치 중 (v2.0.0)", false),
            (Phase::Unsupported, "업데이트 미지원 (v1.0.0)", false),
        ];
        for (phase, korean, clickable) in cases {
            assert_eq!(phase.labels("1.0.0").0, korean);
            assert!(!phase.labels("1.0.0").1.is_empty());
            assert_eq!(phase.clickable(), clickable);
        }
    }
}
