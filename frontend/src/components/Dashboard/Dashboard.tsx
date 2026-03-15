import { useState } from 'react';
import type { Task } from '../../types';
import './Dashboard.css';

interface Props {
  tasks: Task[];
  onUpdateStatus: (id: number, status: Task['status']) => void;
  onDeleteTask: (id: number) => void;
}

type Filter = 'all' | 'running' | 'done' | 'pending';

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'Все' },
  { key: 'running', label: 'В работе' },
  { key: 'done', label: 'Готово' },
  { key: 'pending', label: 'Ожидание' },
];

const STATUS_ICONS: Record<string, string> = {
  done: '✅',
  running: '⏳',
  pending: '⏸️',
};

const STATUS_LABELS: Record<string, string> = {
  done: 'Готово',
  running: 'В работе',
  pending: 'Ожидание',
};

export function Dashboard({ tasks, onUpdateStatus, onDeleteTask }: Props) {
  const [filter, setFilter] = useState<Filter>('all');
  const [showManage, setShowManage] = useState(false);

  const filtered = filter === 'all' ? tasks : tasks.filter(t => t.status === filter);

  return (
    <div className="dashboard">
      <h3 className="dashboard-title">📋 Задачи</h3>

      {/* Filter pills */}
      <div className="filter-bar">
        {FILTERS.map(f => (
          <button
            key={f.key}
            className={`filter-pill ${filter === f.key ? 'active' : ''}`}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Task cards */}
      <div className="task-list">
        {filtered.length === 0 && (
          <div className="task-empty">Нет задач в этой категории.</div>
        )}
        {filtered.map(task => (
          <div key={task.id} className="task-card">
            <div className="task-card-left">
              <span className="task-icon">{STATUS_ICONS[task.status] || '❓'}</span>
              <div>
                <div className="task-title">{task.title}</div>
                <div className="task-meta">
                  {task.ts}
                  {task.type && <span className="badge badge-type">{task.type}</span>}
                </div>
              </div>
            </div>
            <span className={`badge badge-${task.status}`}>
              {STATUS_LABELS[task.status] || '?'}
            </span>
          </div>
        ))}
      </div>

      {/* Manage */}
      <button
        className="manage-toggle"
        onClick={() => setShowManage(v => !v)}
      >
        🔧 Управление задачами {showManage ? '▲' : '▼'}
      </button>

      {showManage && (
        <div className="manage-list">
          {tasks.map(task => (
            <div key={task.id} className="manage-row">
              <span className="manage-title">{task.title}</span>
              <select
                className="manage-select"
                value={task.status}
                onChange={e => onUpdateStatus(task.id, e.target.value as Task['status'])}
              >
                <option value="pending">Ожидание</option>
                <option value="running">В работе</option>
                <option value="done">Готово</option>
              </select>
              <button className="manage-delete" onClick={() => onDeleteTask(task.id)}>🗑</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
