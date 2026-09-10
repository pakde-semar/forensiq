"""
Time Tracking plugin — investigator clock-in/out, time log, and CSV export per case.
"""
import html as _html
from datetime import datetime

TAB_LABEL = "Time Log"
TAB_ICON  = "fa-clock"


def _fmt(minutes: int | None) -> str:
    if not minutes:
        return "—"
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m"


def render_tab(case) -> str:
    case_id = case.id

    # Build investigator rows
    inv_rows = ""
    total_minutes = 0
    inv_options   = ""

    for inv in case.investigators:
        open_entry = next(
            (e for e in inv.time_entries if e.clock_out is None and e.entry_type == "clockinout"),
            None,
        )
        clocked_in   = open_entry is not None
        total_minutes += inv.timeclock_minutes or 0
        total_fmt     = _fmt(inv.timeclock_minutes)
        badge_cls     = "success" if clocked_in else "secondary"
        badge_txt     = "IN" if clocked_in else "OUT"
        lead_badge    = ' <span class="badge bg-primary" style="font-size:.6rem">Lead</span>' if inv.is_lead else ""
        inv_name_esc  = _html.escape(inv.name)

        if clocked_in:
            since = open_entry.clock_in.strftime("%H:%M")
            action_btn = f"""
            <form method="post" action="/cases/{case_id}/investigators/{inv.id}/clockout" class="d-inline">
              <input type="hidden" name="activity" value="">
              <button class="btn btn-sm btn-outline-danger py-0" title="Clock out">
                <i class="fa fa-stop me-1"></i>Clock out (since {since})
              </button>
            </form>"""
        else:
            action_btn = f"""
            <form method="post" action="/cases/{case_id}/investigators/{inv.id}/clockin" class="d-inline">
              <input type="hidden" name="activity" value="">
              <button class="btn btn-sm btn-outline-success py-0" title="Clock in">
                <i class="fa fa-play me-1"></i>Clock in
              </button>
            </form>"""

        inv_rows += f"""
        <tr>
          <td>
            {inv_name_esc}{lead_badge}
            <div class="text-muted" style="font-size:.72rem">{_html.escape(inv.email or '')}</div>
          </td>
          <td><span class="badge bg-{badge_cls}" style="width:2.5rem">{badge_txt}</span></td>
          <td class="fw-semibold">{total_fmt}</td>
          <td class="text-end">{action_btn}</td>
        </tr>"""

        inv_options += f'<option value="{inv.id}">{inv_name_esc}</option>'

    if not case.investigators:
        inv_rows = '<tr><td colspan="4" class="text-muted small p-3">No investigators on this case.</td></tr>'

    # Build time entry log
    entry_rows = ""
    all_entries = sorted(case.time_entries, key=lambda e: e.clock_in, reverse=True)
    inv_name_map = {inv.id: inv.name for inv in case.investigators}

    for e in all_entries[:100]:
        inv_name = _html.escape(inv_name_map.get(e.investigator_id, "?"))
        cin      = e.clock_in.strftime("%Y-%m-%d %H:%M") if e.clock_in else "—"
        cout     = e.clock_out.strftime("%H:%M") if e.clock_out else '<span class="text-success">OPEN</span>'
        dur      = _fmt(e.duration_minutes)
        act      = _html.escape(e.activity or "")
        typ_badge = ('<span class="badge bg-secondary" style="font-size:.6rem">manual</span>'
                     if e.entry_type == "manual" else "")

        entry_rows += f"""
        <tr>
          <td class="small">{inv_name}</td>
          <td class="small font-monospace">{cin}</td>
          <td class="small font-monospace">{cout}</td>
          <td class="small">{dur}</td>
          <td class="small text-muted">{act} {typ_badge}</td>
          <td class="text-end">
            <form method="post" action="/cases/{case_id}/time/entries/{e.id}/delete"
                  onsubmit="return confirm('Delete this time entry?')">
              <button class="btn btn-sm py-0 btn-outline-danger"><i class="fa fa-trash"></i></button>
            </form>
          </td>
        </tr>"""

    if not entry_rows:
        entry_rows = '<tr><td colspan="6" class="text-muted small p-3">No time entries yet.</td></tr>'

    today = datetime.utcnow().strftime("%Y-%m-%d")
    now   = datetime.utcnow().strftime("%H:%M")

    return f"""
<div class="row g-3 mt-1">

  <!-- Left: investigator summary -->
  <div class="col-md-5">
    <div class="card mb-3">
      <div class="card-header d-flex justify-content-between align-items-center">
        <span><i class="fa fa-users me-1"></i>Investigators</span>
        <span class="badge bg-secondary">{_fmt(total_minutes)} total</span>
      </div>
      <div class="card-body p-0">
        <table class="table table-sm table-dark mb-0 align-middle">
          <thead class="table-secondary text-muted small">
            <tr><th>Name</th><th>Status</th><th>Hours</th><th></th></tr>
          </thead>
          <tbody>{inv_rows}</tbody>
        </table>
      </div>
    </div>

    <!-- Manual entry form -->
    <div class="card">
      <div class="card-header"><i class="fa fa-pen-to-square me-1"></i>Add manual entry</div>
      <div class="card-body">
        <form method="post" action="/cases/{case_id}/time/manual">
          <div class="mb-2">
            <label class="form-label small">Investigator</label>
            <select name="inv_id" class="form-select form-select-sm" required>
              {inv_options or '<option value="">— no investigators —</option>'}
            </select>
          </div>
          <div class="row g-2 mb-2">
            <div class="col-6">
              <label class="form-label small">Date in</label>
              <input type="date" name="date_in" class="form-control form-control-sm"
                     value="{today}" required>
            </div>
            <div class="col-6">
              <label class="form-label small">Time in</label>
              <input type="time" name="time_in" class="form-control form-control-sm"
                     value="09:00" required>
            </div>
          </div>
          <div class="row g-2 mb-2">
            <div class="col-6">
              <label class="form-label small">Date out</label>
              <input type="date" name="date_out" class="form-control form-control-sm"
                     value="{today}" required>
            </div>
            <div class="col-6">
              <label class="form-label small">Time out</label>
              <input type="time" name="time_out" class="form-control form-control-sm"
                     value="{now}" required>
            </div>
          </div>
          <div class="mb-2">
            <label class="form-label small">Activity note</label>
            <input type="text" name="activity" class="form-control form-control-sm"
                   placeholder="e.g. Disk imaging, Log analysis…">
          </div>
          <button class="btn btn-sm btn-outline-primary w-100">
            <i class="fa fa-plus me-1"></i>Add entry
          </button>
        </form>
      </div>
    </div>
  </div>

  <!-- Right: time log table -->
  <div class="col-md-7">
    <div class="card">
      <div class="card-header d-flex justify-content-between align-items-center">
        <span><i class="fa fa-list-check me-1"></i>Time log</span>
        <a href="/cases/{case_id}/time/export.csv"
           class="btn btn-sm btn-outline-secondary py-0" download>
          <i class="fa fa-file-csv me-1"></i>Export CSV
        </a>
      </div>
      <div class="card-body p-0" style="max-height:520px;overflow-y:auto">
        <table class="table table-sm table-dark mb-0 align-middle">
          <thead class="table-secondary text-muted small" style="position:sticky;top:0">
            <tr>
              <th>Investigator</th>
              <th>Clock in</th>
              <th>Clock out</th>
              <th>Duration</th>
              <th>Activity</th>
              <th></th>
            </tr>
          </thead>
          <tbody>{entry_rows}</tbody>
        </table>
      </div>
    </div>
  </div>

</div>
"""
