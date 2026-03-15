export interface FileNode {
  _type: 'file';
  content: string;
}

export interface FolderNode {
  _type: 'folder';
  _open: boolean;
  [key: string]: WorkspaceNode | string | boolean;
}

export type WorkspaceNode = FileNode | FolderNode;

export interface Workspace {
  [key: string]: WorkspaceNode;
}

export interface Task {
  id: number;
  title: string;
  status: 'done' | 'running' | 'pending';
  ts: string;
  type: string;
}

export interface ChatMessage {
  role: 'user' | 'ai';
  text: string;
}

export type View = 'home' | 'file';
