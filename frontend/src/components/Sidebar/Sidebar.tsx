import { useState } from 'react';
import type { Workspace, WorkspaceNode, FolderNode } from '../../types';
import './Sidebar.css';

interface Props {
  workspace: Workspace;
  selectedPath: string[] | null;
  onOpenFile: (path: string[]) => void;
  onGoHome: () => void;
  onToggleFolder: (path: string[]) => void;
  onCreateFile: (parentPath: string[], name: string) => void;
  onCreateFolder: (parentPath: string[], name: string) => void;
}

export function Sidebar({
  workspace, selectedPath, onOpenFile, onGoHome,
  onToggleFolder, onCreateFile, onCreateFolder,
}: Props) {
  const [creatingIn, setCreatingIn] = useState<string | null>(null);
  const [newName, setNewName] = useState('');

  const handleCreate = (parentPath: string[], asFolder: boolean) => {
    const name = newName.trim();
    if (!name) return;
    if (asFolder) {
      onCreateFolder(parentPath, name);
    } else {
      onCreateFile(parentPath, name);
    }
    setCreatingIn(null);
    setNewName('');
  };

  const renderTree = (node: Record<string, any>, path: string[], depth: number = 0) => {
    const entries = Object.keys(node).filter(k => !k.startsWith('_')).sort();

    return entries.map(key => {
      const value = node[key] as WorkspaceNode;
      const currentPath = [...path, key];
      const pathStr = currentPath.join('/');

      if (value._type === 'folder') {
        const folder = value as FolderNode;
        const isOpen = folder._open;

        return (
          <div key={pathStr} className="tree-folder">
            <button
              className="tree-folder-btn"
              onClick={() => onToggleFolder(currentPath)}
              style={{ paddingLeft: `${8 + depth * 16}px` }}
            >
              <span className="tree-arrow">{isOpen ? '▼' : '▶'}</span>
              <span className="tree-icon">📁</span>
              <span className="tree-label">{key}</span>
            </button>

            {isOpen && (
              <div className="tree-children">
                {renderTree(folder as Record<string, any>, currentPath, depth + 1)}

                {/* Inline create */}
                {creatingIn === pathStr ? (
                  <div className="tree-create-form" style={{ paddingLeft: `${24 + depth * 16}px` }}>
                    <input
                      className="tree-create-input"
                      value={newName}
                      onChange={e => setNewName(e.target.value)}
                      placeholder="имя_файла.md"
                      autoFocus
                      onKeyDown={e => {
                        if (e.key === 'Enter') handleCreate(currentPath, false);
                        if (e.key === 'Escape') { setCreatingIn(null); setNewName(''); }
                      }}
                    />
                    <div className="tree-create-actions">
                      <button onClick={() => handleCreate(currentPath, false)} title="Файл">📄</button>
                      <button onClick={() => handleCreate(currentPath, true)} title="Папка">📁</button>
                      <button onClick={() => { setCreatingIn(null); setNewName(''); }}>✕</button>
                    </div>
                  </div>
                ) : (
                  <button
                    className="tree-add-btn"
                    style={{ paddingLeft: `${24 + depth * 16}px` }}
                    onClick={() => { setCreatingIn(pathStr); setNewName(''); }}
                  >
                    ＋ Создать…
                  </button>
                )}
              </div>
            )}
          </div>
        );
      }

      // File
      const isSelected = selectedPath?.join('/') === pathStr;
      return (
        <button
          key={pathStr}
          className={`tree-file-btn ${isSelected ? 'active' : ''}`}
          style={{ paddingLeft: `${8 + depth * 16}px` }}
          onClick={() => onOpenFile(currentPath)}
        >
          <span className="tree-icon">{key.endsWith('.md') ? '📝' : '📄'}</span>
          <span className="tree-label">{key}</span>
        </button>
      );
    });
  };

  return (
    <aside className="sidebar">
      <button className="sidebar-home-btn" onClick={onGoHome}>
        🏠 Главная
      </button>

      <div className="sidebar-section-label">Проводник</div>

      <nav className="sidebar-tree">
        {renderTree(workspace as Record<string, any>, [])}
      </nav>
    </aside>
  );
}
