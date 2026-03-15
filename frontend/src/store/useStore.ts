import { useState, useCallback } from 'react';
import type { Workspace, Task, ChatMessage, View, WorkspaceNode, FolderNode } from '../types';

const DEFAULT_WORKSPACE: Workspace = {
  'Проекты': {
    _type: 'folder',
    _open: true,
    'AI BOS': {
      _type: 'folder',
      _open: true,
      'PRD.md': { _type: 'file', content: '# PRD — AI Business Operating System\n\nОписание продукта…' },
      'Архитектура.md': { _type: 'file', content: '# Архитектура\n\n## Компоненты\n- Frontend (React + Vite)\n- Backend API\n- LLM Service' },
      'Бэклог.md': { _type: 'file', content: '# Бэклог\n\n- [ ] MVP интерфейса\n- [ ] Интеграция с LLM\n- [ ] Система задач' },
    } as FolderNode,
    'Маркетинг': {
      _type: 'folder',
      _open: false,
      'Стратегия.md': { _type: 'file', content: '# Маркетинговая стратегия\n\n## Каналы\n1. SEO\n2. Content marketing\n3. Community' },
    } as FolderNode,
  } as FolderNode,
  'Документы': {
    _type: 'folder',
    _open: false,
    'Заметки.md': { _type: 'file', content: '# Заметки\n\nРабочие заметки и идеи…' },
    'Шаблон отчёта.md': { _type: 'file', content: '# Отчёт\n\n## Период: …\n## Результаты\n…' },
  } as FolderNode,
  'Данные': {
    _type: 'folder',
    _open: false,
    'KPI Q1.md': { _type: 'file', content: '# KPI Q1 2026\n\n| Метрика | План | Факт |\n|---------|------|------|\n| Revenue | 100k | 95k  |\n| Users   | 10k  | 12k  |' },
  } as FolderNode,
};

const DEFAULT_TASKS: Task[] = [
  { id: 1, title: 'Сгенерировать PRD', status: 'done', ts: '14:02', type: 'LLM' },
  { id: 2, title: 'Проанализировать KPI', status: 'running', ts: '14:15', type: 'LLM' },
  { id: 3, title: 'Подготовить отчёт', status: 'pending', ts: '—', type: 'MCP' },
];

function getNode(workspace: Workspace, path: string[]): WorkspaceNode | null {
  let node: any = workspace;
  for (const part of path) {
    if (node && typeof node === 'object' && part in node) {
      node = node[part];
    } else {
      return null;
    }
  }
  return node;
}

function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj));
}

export function useStore() {
  const [workspace, setWorkspace] = useState<Workspace>(DEFAULT_WORKSPACE);
  const [view, setView] = useState<View>('home');
  const [selectedPath, setSelectedPath] = useState<string[] | null>(null);
  const [openTabs, setOpenTabs] = useState<string[][]>([]);
  const [editing, setEditing] = useState(false);
  const [tasks, setTasks] = useState<Task[]>(DEFAULT_TASKS);
  const [nextTaskId, setNextTaskId] = useState(4);
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);

  const getFileContent = useCallback((path: string[]): string => {
    const node = getNode(workspace, path);
    if (node && node._type === 'file') return node.content;
    return '';
  }, [workspace]);

  const openFile = useCallback((path: string[]) => {
    setSelectedPath(path);
    setView('file');
    setEditing(false);
    setOpenTabs(prev => {
      const key = path.join('/');
      if (prev.some(t => t.join('/') === key)) return prev;
      return [...prev, path];
    });
  }, []);

  const closeTab = useCallback((idx: number) => {
    setOpenTabs(prev => {
      const next = [...prev];
      const closed = next.splice(idx, 1)[0];
      if (selectedPath && selectedPath.join('/') === closed.join('/')) {
        if (next.length > 0) {
          setSelectedPath(next[next.length - 1]);
        } else {
          setSelectedPath(null);
          setView('home');
        }
      }
      return next;
    });
    setEditing(false);
  }, [selectedPath]);

  const switchTab = useCallback((path: string[]) => {
    setSelectedPath(path);
    setEditing(false);
  }, []);

  const goHome = useCallback(() => {
    setView('home');
    setSelectedPath(null);
    setEditing(false);
  }, []);

  const toggleFolder = useCallback((path: string[]) => {
    setWorkspace(prev => {
      const ws = deepClone(prev);
      const node = getNode(ws, path);
      if (node && node._type === 'folder') {
        (node as FolderNode)._open = !node._open;
      }
      return ws;
    });
  }, []);

  const saveContent = useCallback((path: string[], content: string) => {
    setWorkspace(prev => {
      const ws = deepClone(prev);
      let node: any = ws;
      for (const part of path.slice(0, -1)) node = node[part];
      node[path[path.length - 1]].content = content;
      return ws;
    });
    setEditing(false);
  }, []);

  const createFile = useCallback((parentPath: string[], name: string) => {
    setWorkspace(prev => {
      const ws = deepClone(prev);
      let node: any = ws;
      for (const part of parentPath) node = node[part];
      node[name] = { _type: 'file', content: `# ${name}\n\n` };
      return ws;
    });
    const filePath = [...parentPath, name];
    openFile(filePath);
    createTask(`Создание: ${name}`, 'Code');
  }, [openFile]);

  const createFolder = useCallback((parentPath: string[], name: string) => {
    setWorkspace(prev => {
      const ws = deepClone(prev);
      let node: any = ws;
      for (const part of parentPath) node = node[part];
      node[name] = { _type: 'folder', _open: true };
      return ws;
    });
  }, []);

  const createTask = useCallback((title: string, type: string = 'LLM') => {
    const now = new Date();
    const ts = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    setTasks(prev => [...prev, {
      id: nextTaskId,
      title,
      status: 'running',
      ts,
      type,
    }]);
    setNextTaskId(prev => prev + 1);
  }, [nextTaskId]);

  const updateTaskStatus = useCallback((id: number, status: Task['status']) => {
    setTasks(prev => prev.map(t => t.id === id ? { ...t, status } : t));
  }, []);

  const deleteTask = useCallback((id: number) => {
    setTasks(prev => prev.filter(t => t.id !== id));
  }, []);

  const sendMessage = useCallback((text: string) => {
    setChatHistory(prev => {
      const ctx = selectedPath ? `\n\n*(Контекст: ${selectedPath[selectedPath.length - 1]})*` : '';
      const aiResp = `Принято! Обработаю запрос: «${text}».${ctx}\n\n_Подключите API для реальных ответов._`;
      return [
        ...prev,
        { role: 'user', text },
        { role: 'ai', text: aiResp },
      ];
    });
    const short = text.length > 50 ? text.slice(0, 50) + '…' : text;
    createTask(short, 'LLM');
  }, [selectedPath, createTask]);

  return {
    workspace, view, selectedPath, openTabs, editing, tasks, chatHistory,
    setEditing, openFile, closeTab, switchTab, goHome, toggleFolder,
    saveContent, createFile, createFolder, createTask,
    updateTaskStatus, deleteTask, sendMessage, getFileContent,
  };
}
