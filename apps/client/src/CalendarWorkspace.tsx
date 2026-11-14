import { useMemo, useRef, useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, Plus, Inbox, Minus, CalendarDays } from 'lucide-react';
import type { Work } from './taskModels';
import {
  addDays,
  calendarDays,
  calendarEvents,
  dayKey,
  eventLanes,
  type CalendarScale,
} from './calendarModel';
import './calendar.css';
const time = (date: Date) => date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const stateLabel: Record<string, string> = {
  scheduled: '已安排',
  running: '进行中',
  ready: '等待开始',
  delivering: '正在送达',
  succeeded: '已完成',
  blocked: '需要关注',
  failed: '未完成',
  cancelled: '已取消',
  expired: '已过期',
  paused: '已暂停',
};
export function CalendarWorkspace({
  tasks,
  loaded,
  onSelect,
  onCreate,
}: {
  tasks: Work[];
  loaded: boolean;
  onSelect: (id: string) => void;
  onCreate: (date?: Date) => void;
}) {
  const [focus, setFocus] = useState(new Date()),
    [scale, setScale] = useState<CalendarScale>('month');
  const [inbox, setInbox] = useState(false),
    [height, setHeight] = useState(72);
  const grid = useRef<HTMLDivElement>(null);
  const days = useMemo(() => calendarDays(focus, scale), [focus, scale]);
  const events = useMemo(() => calendarEvents(tasks, days), [tasks, days]);
  const selected = events.filter((e) => dayKey(e.date) === dayKey(focus));
  const unscheduled = tasks.filter(
    (t) =>
      ['now', ''].includes(t.schedule.mode) &&
      !['succeeded', 'cancelled', 'expired'].includes(
        t.state === 'active' ? t.runs[0]?.status || '' : t.state,
      ),
  );
  useEffect(() => {
    if (grid.current) grid.current.scrollTop = 7 * height;
  }, [scale]);
  function move(n: number) {
    if (scale === 'month') {
      const next = new Date(focus.getFullYear(), focus.getMonth() + n, 1);
      setFocus(next);
    } else setFocus(addDays(focus, n * (scale === 'week' ? 7 : 1)));
  }
  function create() {
    const date = new Date(focus);
    date.setHours(9, 0, 0, 0);
    onCreate(date);
  }
  return (
    <div className="calendar-workspace">
      <header className="calendar-toolbar">
        <div className="calendar-period">
          <span>{focus.getFullYear()}</span>
          <h3>{focus.toLocaleDateString([], { month: 'long' })}</h3>
        </div>
        <div className="calendar-navigation">
          <button
            onClick={() => {
              setFocus(new Date());
              setInbox(false);
            }}
          >
            今天
          </button>
          <button aria-label="上一页" onClick={() => move(-1)}>
            <ChevronLeft size={17} />
          </button>
          <button aria-label="下一页" onClick={() => move(1)}>
            <ChevronRight size={17} />
          </button>
        </div>
        <div className="calendar-scales" aria-label="日历视图">
          {(['month', 'week', 'day'] as const).map((value, index) => (
            <button
              key={value}
              aria-pressed={!inbox && scale === value}
              onClick={() => {
                setScale(value);
                setInbox(false);
              }}
            >
              {['月', '周', '日'][index]}
            </button>
          ))}
        </div>
        <button
          className={`calendar-inbox ${inbox ? 'selected' : ''}`}
          onClick={() => setInbox(!inbox)}
        >
          <Inbox size={16} />
          待安排 <span>{unscheduled.length}</span>
        </button>
        <button className="calendar-add" onClick={create}>
          <Plus size={16} />
          新建安排
        </button>
      </header>
      {inbox ? (
        <div className="calendar-inbox-content">
          <h3>尚未放进日历</h3>
          <p>没有指定时间的事情留在这里。</p>
          {unscheduled.length === 0 && <p>暂时没有待安排的事。</p>}
          {unscheduled.map((task) => (
            <button key={task.id} onClick={() => onSelect(task.id)}>
              <CalendarDays size={18} />
              <span>
                <strong>{task.title}</strong>
                <small>
                  {
                    stateLabel[
                      task.state === 'active' ? task.runs[0]?.status || 'scheduled' : task.state
                    ]
                  }{' '}
                  · {task.objective}
                </small>
              </span>
              <ChevronRight size={16} />
            </button>
          ))}
        </div>
      ) : scale === 'month' ? (
        <>
          <div className="calendar-weekdays">
            {['一', '二', '三', '四', '五', '六', '日'].map((d) => (
              <span key={d}>周{d}</span>
            ))}
          </div>
          <div className="calendar-month" role="group" aria-label="月历">
            {days.map((day) => {
              const values = events.filter((e) => dayKey(e.date) === dayKey(day));
              return (
                <div
                  key={dayKey(day)}
                  className={`calendar-cell ${day.getMonth() !== focus.getMonth() ? 'outside' : ''} ${dayKey(day) === dayKey(focus) ? 'selected' : ''}`}
                >
                  <button
                    className={`calendar-date ${dayKey(day) === dayKey(new Date()) ? 'today' : ''}`}
                    aria-label={day.toLocaleDateString([], { dateStyle: 'full' })}
                    aria-pressed={dayKey(day) === dayKey(focus)}
                    onClick={() => setFocus(day)}
                    onDoubleClick={() => {
                      setFocus(day);
                      setScale('day');
                    }}
                  >
                    {day.getDate()}
                  </button>
                  {values.slice(0, 3).map((event) => (
                    <button
                      className={`calendar-event ${event.status}`}
                      key={event.id}
                      onClick={() => onSelect(event.task.id)}
                      title={`${time(event.date)} ${event.task.title} · ${event.projected ? '重复安排' : stateLabel[event.status] || event.status}`}
                    >
                      <time>{time(event.date)}</time>
                      <span>{event.task.title}</span>
                    </button>
                  ))}
                  {values.length > 3 && (
                    <button
                      className="calendar-more"
                      onClick={() => {
                        setFocus(day);
                        setScale('day');
                      }}
                    >
                      还有 {values.length - 3} 项
                    </button>
                  )}
                </div>
              );
            })}
          </div>
          <footer className="calendar-footer">
            <span>
              {focus.toLocaleDateString([], { month: 'long', day: 'numeric', weekday: 'long' })}
            </span>
            <span>{selected.length ? `${selected.length} 项安排` : '这一天，留点空白。'}</span>
            <button onClick={() => setScale('day')}>
              查看当天 <ChevronRight size={14} />
            </button>
          </footer>
        </>
      ) : (
        <>
          <div className="calendar-time-toolbar">
            <span>{Intl.DateTimeFormat().resolvedOptions().timeZone} · 计划开始时间</span>
            <div>
              <button
                aria-label="缩小时间轴"
                disabled={height <= 48}
                onClick={() => setHeight(Math.max(48, height - 24))}
              >
                <Minus size={15} />
              </button>
              <span>{Math.round((height / 72) * 100)}%</span>
              <button
                aria-label="放大时间轴"
                disabled={height >= 144}
                onClick={() => setHeight(Math.min(144, height + 24))}
              >
                <Plus size={15} />
              </button>
            </div>
          </div>
          <div className="calendar-time-scroll" ref={grid}>
            <div
              className="calendar-time-heading"
              style={{
                gridTemplateColumns: `50px repeat(${days.length},minmax(${scale === 'day' ? '220' : '100'}px,1fr))`,
              }}
            >
              <span />
              {days.map((day) => (
                <button
                  key={dayKey(day)}
                  className={dayKey(day) === dayKey(focus) ? 'selected' : ''}
                  onClick={() => setFocus(day)}
                >
                  {day.toLocaleDateString([], { weekday: 'short' })}
                  <strong>{day.getDate()}</strong>
                </button>
              ))}
            </div>
            <div
              className="calendar-time-body"
              style={{
                gridTemplateColumns: `50px repeat(${days.length},minmax(${scale === 'day' ? '220' : '100'}px,1fr))`,
                height: 24 * height + 64,
              }}
            >
              <div className="calendar-hours">
                {Array.from({ length: 24 }, (_, h) => (
                  <span key={h} style={{ top: h * height }}>
                    {String(h).padStart(2, '0')}:00
                  </span>
                ))}
              </div>
              {days.map((day) => (
                <div
                  key={dayKey(day)}
                  className="calendar-time-column"
                  style={{ backgroundSize: `100% ${height}px` }}
                >
                  {eventLanes(
                    events.filter((e) => dayKey(e.date) === dayKey(day)),
                    height,
                  ).map(({ event, lane, lanes }) => (
                    <button
                      className={`calendar-time-event ${event.status}`}
                      key={event.id}
                      style={{
                        top: (event.date.getHours() + event.date.getMinutes() / 60) * height,
                        left: `calc(${(lane / lanes) * 100}% + 3px)`,
                        width: `calc(${100 / lanes}% - 6px)`,
                      }}
                      onClick={() => onSelect(event.task.id)}
                    >
                      <time>{time(event.date)}</time>
                      <strong>{event.task.title}</strong>
                      <small>{event.projected ? '重复安排' : stateLabel[event.status]}</small>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </>
      )}
      {!loaded && (
        <div className="calendar-loading" role="status">
          正在读取日程…
        </div>
      )}
    </div>
  );
}
