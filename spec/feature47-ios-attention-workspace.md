# iOS attention workspace

Status: Implemented

## Product

Home uses a single contextual focus (approval, user decision, upcoming personal arrangement or a recent result). Two smaller surfaces show the next personal time and the agent's current/recent work. Installed application shortcuts and one optional grounded inspiration follow. It does not duplicate every task lane or assign equal visual weight to all modules.

Tasks opens with four explicit modes: month, week, day and status. Month shows a seven-column overview
and the selected day's agenda. Week keeps all seven dates visible while the selected day occupies a
single time grid. Day focuses one date. Status groups work into attention, active, scheduled, unscheduled
and finished lanes, with direct filters for each lane. Selection survives calendar mode changes.

## Visual system

The visual hierarchy comes from scale and position: a large date with a small otter, one main action, a paired time/status row, and a quiet paper-toned inspiration. Avoid repeated section rails and status headlines. Use system Dynamic Type with ink, muted, blue and attention roles from Brand; subtle material belongs to navigation controls, not every content surface.

## Performance

Calendar events are built once per selected period and indexed by day instead of filtering the full
collection for all 42 month cells. Task lanes are grouped once whenever task data changes, so status
counts and filters do not rescan the task list for every chip. Only the selected day receives a time
grid in week and day modes. No network polling is added by this workspace.

## Verification

UI tests cover Home priority order and switching between calendar and status views. Simulator checks
cover light and dark appearance, Dynamic Type accessibility sizes, month, week, day and status modes,
and the existing streaming performance preview. Empty and populated previews use synthetic data only.
