// 与后端 backend/main.py + layout.py + progress.py 对应的类型

export type NodeState = 'done' | 'learning' | 'locked'

export interface Task {
  id: string
  title: string
  done: boolean
  resource?: string
  verify?: Task[]   // 验收子任务（挂在该学习知识点下）
}

export interface NodeDir { id: string; color: string; branch: string }

export interface GraphNode {
  id: string
  name: string
  category: string
  tasks: Task[]
  depends_on: string[]
  x: number           // 基础布局 x（未含避让）
  y: number           // 基础布局 y
  depth: number
  dirs: NodeDir[]
  mastered: number
  total_points: number
  pct: number
  state: NodeState
  status_hint: string
}

export interface Edge { from: string; to: string }

export interface Canvas { w: number; h: number }

export interface LayoutConstants {
  NODE_W: number; NODE_H: number; COL_GAP: number; ROW_GAP: number; CANVAS_PAD: number
}

export interface DirOrder {
  id: string; title: string; icon: string; color: string; subtitle: string
}

export interface Achievement {
  def: { id: string; icon: string; name: string; desc: string; tier: 'bronze' | 'silver' | 'gold' }
  unlocked: boolean
}

export interface Overview {
  overall_pct: number
  mastered_points: number
  total_points: number
  done_nodes: number
  total_nodes: number
  achievements_unlocked: number
  achievements_total: number
  tree_count: number
}

export interface Graph {
  nodes: GraphNode[]
  edges: Edge[]
  canvas: Canvas
  constants: LayoutConstants
  dir_order: DirOrder[]
  achievements: Achievement[]
  overview: Overview
}

// 其他板块
export interface Profile {
  name: string; name_en?: string; tagline?: string
  contact: { email?: string; phone?: string; github?: string; github_url?: string }
  education: { school: string; period: string; degree: string; major: string }[]
  skills: { group: string; items: string[] }[]
  experience: {
    title: string; period: string; role: string; tech?: string[]
    url?: string; desc?: string; highlights?: string[]
  }[]
  awards: { title: string; year: string | number; note?: string }[]
  leadership?: string[]
}

export interface Template {
  id: string; name: string; style: string; lang: string; scene: string; star?: boolean
}

export interface Fruit {
  id: string; title: string; icon: string; subtitle: string
  color: string; pct: number; has_pdf: boolean
}
