import { useState, useEffect } from 'react';
import './Editor.css';

interface Props {
  selectedPath: string[] | null;
  openTabs: string[][];
  editing: boolean;
  content: string;
  onSetEditing: (v: boolean) => void;
  onSaveContent: (path: string[], content: string) => void;
  onCloseTab: (idx: number) => void;
  onSwitchTab: (path: string[]) => void;
}

export function Editor({
  selectedPath, openTabs, editing, content,
  onSetEditing, onSaveContent, onCloseTab, onSwitchTab,
}: Props) {
  const [editBuffer, setEditBuffer] = useState(content);

  useEffect(() => {
    setEditBuffer(content);
  }, [content, selectedPath?.join('/')]);

  if (!selectedPath) return null;

  const fname = selectedPath[selectedPath.length - 1];
  const breadcrumb = selectedPath.slice(0, -1).join(' / ');

  const handleSave = () => {
    onSaveContent(selectedPath, editBuffer);
  };

  // Simple markdown-to-html (headings, bold, italic, lists, tables, code)
  const renderMarkdown = (md: string) => {
    const lines = md.split('\n');
    const html: string[] = [];
    let inTable = false;

    for (const line of lines) {
      // Headings
      if (line.startsWith('### ')) {
        html.push(`<h3>${line.slice(4)}</h3>`);
      } else if (line.startsWith('## ')) {
        html.push(`<h2>${line.slice(3)}</h2>`);
      } else if (line.startsWith('# ')) {
        html.push(`<h1>${line.slice(2)}</h1>`);
      }
      // Table
      else if (line.trim().startsWith('|')) {
        if (line.trim().match(/^\|[\s-|]+\|$/)) continue; // separator row
        if (!inTable) { html.push('<table>'); inTable = true; }
        const cells = line.split('|').filter(c => c.trim() !== '').map(c => c.trim());
        html.push(`<tr>${cells.map(c => `<td>${c}</td>`).join('')}</tr>`);
      }
      // List items
      else if (line.trim().startsWith('- [ ] ')) {
        html.push(`<div class="md-checkbox">☐ ${line.trim().slice(6)}</div>`);
      } else if (line.trim().startsWith('- [x] ')) {
        html.push(`<div class="md-checkbox done">☑ ${line.trim().slice(6)}</div>`);
      } else if (line.trim().startsWith('- ')) {
        if (inTable) { html.push('</table>'); inTable = false; }
        html.push(`<div class="md-list-item">• ${applyInline(line.trim().slice(2))}</div>`);
      } else if (line.trim().match(/^\d+\.\s/)) {
        if (inTable) { html.push('</table>'); inTable = false; }
        html.push(`<div class="md-list-item">${applyInline(line.trim())}</div>`);
      }
      // Empty line
      else if (line.trim() === '') {
        if (inTable) { html.push('</table>'); inTable = false; }
        html.push('<br/>');
      }
      // Paragraph
      else {
        if (inTable) { html.push('</table>'); inTable = false; }
        html.push(`<p>${applyInline(line)}</p>`);
      }
    }
    if (inTable) html.push('</table>');
    return html.join('\n');
  };

  const applyInline = (text: string): string => {
    return text
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/_(.+?)_/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code>$1</code>');
  };

  return (
    <div className="editor">
      {/* Tab bar */}
      {openTabs.length > 0 && (
        <div className="tab-bar">
          {openTabs.map((tab, idx) => {
            const isActive = selectedPath.join('/') === tab.join('/');
            return (
              <div
                key={tab.join('/')}
                className={`tab-item ${isActive ? 'active' : ''}`}
                onClick={() => !isActive && onSwitchTab(tab)}
              >
                <span className="tab-name">{tab[tab.length - 1]}</span>
                <span
                  className="tab-close"
                  onClick={e => { e.stopPropagation(); onCloseTab(idx); }}
                >
                  ✕
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Content area */}
      <div className="editor-content">
        {editing ? (
          <>
            <div className="editor-toolbar">
              <span className="editor-label">✏️ Редактирование: {fname}</span>
            </div>
            <textarea
              className="editor-textarea"
              value={editBuffer}
              onChange={e => setEditBuffer(e.target.value)}
              autoFocus
            />
            <div className="editor-actions">
              <button className="btn btn-primary" onClick={handleSave}>💾 Сохранить</button>
              <button className="btn btn-ghost" onClick={() => onSetEditing(false)}>Отмена</button>
            </div>
          </>
        ) : (
          <>
            <div className="editor-header">
              <div className="editor-file-info">
                <span className="editor-breadcrumb">📁 {breadcrumb}</span>
                <span className="editor-filename">{fname}</span>
              </div>
              <button className="btn btn-ghost" onClick={() => onSetEditing(true)}>
                ✏️ Редактировать
              </button>
            </div>
            <div className="editor-separator" />
            <div
              className="editor-markdown"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
            />
          </>
        )}
      </div>
    </div>
  );
}
