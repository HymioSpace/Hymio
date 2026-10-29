import type { Work } from './taskModels';
export type CalendarEvent = {
  id: string;
  task: Work;
  date: Date;
  status: string;
  projected: boolean;
};
export type CalendarScale = 'month' | 'week' | 'day';
export function dayKey(date: Date) {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}
export function addDays(date: Date, days: number) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}
export function calendarDays(focus: Date, scale: CalendarScale) {
  let start = new Date(focus.getFullYear(), focus.getMonth(), focus.getDate());
  if (scale === 'month') start.setDate(1);
  if (scale !== 'day') start = addDays(start, -(start.getDay() + 6) % 7);
  return Array.from({ length: scale === 'month' ? 42 : scale === 'week' ? 7 : 1 }, (_, i) =>
    addDays(start, i),
  );
}
const zoneFormatters = new Map<string, Intl.DateTimeFormat>();
function zonedParts(date: Date, timezone: string) {
  let formatter = zoneFormatters.get(timezone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat('en-GB', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    });
    if (zoneFormatters.size >= 32) zoneFormatters.delete(zoneFormatters.keys().next().value!);
    zoneFormatters.set(timezone, formatter);
  }
  return Object.fromEntries(formatter.formatToParts(date).map((p) => [p.type, p.value]));
}
// Resolve a wall-clock time, checking that DST gaps don't silently move a plan.
function zonedTime(
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number,
  zone: string,
) {
  const wall = Date.UTC(year, month - 1, day, hour, minute);
  let value = wall;
  for (let i = 0; i < 3; i++) {
    const p = zonedParts(new Date(value), zone);
    const adjustment = wall - Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute);
    if (adjustment === 0) break;
    value += adjustment;
  }
  const result = new Date(value),
    p = zonedParts(result, zone);
  return +p.year === year &&
    +p.month === month &&
    +p.day === day &&
    +p.hour === hour &&
    +p.minute === minute
    ? result
    : null;
}
export function calendarEvents(tasks: Work[], days: Date[], now = new Date()): CalendarEvent[] {
  if (!days.length) return [];
  const start = days[0],
    end = addDays(days[days.length - 1], 1);
  const result: CalendarEvent[] = [];
  for (const task of tasks) {
    if (['now', ''].includes(task.schedule.mode)) continue;
    const seen = new Set<number>();
    const insert = (date: Date, status: string, projected = false) => {
      const minute = Math.floor(date.getTime() / 60000);
      if (date >= start && date < end && !seen.has(minute)) {
        seen.add(minute);
        result.push({ id: `${task.id}:${minute}`, task, date, status, projected });
      }
    };
    for (const run of task.runs)
      if (run.due_at > 0) insert(new Date(run.due_at * 1000), run.status);
    if (task.schedule.mode === 'once' && task.schedule.at)
      insert(
        new Date(task.schedule.at),
        task.state === 'active' ? task.runs[0]?.status || 'scheduled' : task.state,
      );
    if (task.state !== 'active' || !['daily', 'weekly'].includes(task.schedule.mode)) continue;
    const zone = task.schedule.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
    const time = /^(\d{2}):(\d{2})$/.exec(task.schedule.time || '');
    if (!time || +time[1] > 23 || +time[2] > 59) continue;
    try {
      // Include timezone offsets at both edges of the viewer's visible interval.
      const p = zonedParts(start, zone),
        base = new Date(Date.UTC(+p.year, +p.month - 1, +p.day));
      for (let i = -1; i <= days.length + 1; i++) {
        const wall = new Date(base);
        wall.setUTCDate(wall.getUTCDate() + i);
        if (task.schedule.mode === 'weekly' && (wall.getUTCDay() + 6) % 7 !== task.schedule.weekday)
          continue;
        const date = zonedTime(
          wall.getUTCFullYear(),
          wall.getUTCMonth() + 1,
          wall.getUTCDate(),
          +time[1],
          +time[2],
          zone,
        );
        if (date && date > now) insert(date, 'scheduled', true);
      }
    } catch {
      /* invalid legacy timezone: retain actual occurrences only */
    }
  }
  return result.sort((a, b) => a.date.getTime() - b.date.getTime());
}
export function eventLanes(events: CalendarEvent[], hourHeight: number) {
  const groups: CalendarEvent[][] = [];
  for (const event of events) {
    const group = groups.at(-1);
    if (group && event.date.getTime() - group.at(-1)!.date.getTime() < (56 / hourHeight) * 3600000)
      group.push(event);
    else groups.push([event]);
  }
  return groups.flatMap((group) =>
    group.map((event, lane) => ({ event, lane, lanes: group.length })),
  );
}
