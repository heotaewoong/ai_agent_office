export type LibraryAction = 'trash' | 'restore' | 'purge';
export type LibraryItem = {
  id: string; title: string; name: string; job_id?: string | null;
  kind: 'video' | 'cards' | 'thumbnail' | 'document';
  state: 'available' | 'trash' | 'attention'; protected_reason: string;
  size_bytes: number; file_count: number; modified_at: string; shared: boolean; preview_url: string | null;
};
export type LibraryInventory = {items: LibraryItem[]; storage: {total_bytes: number; used_bytes: number; free_bytes: number}; checked_at: string};
export type LibraryQuote = {token: string; count: number; size_bytes: number; reclaimable_bytes: number; shared_files: number};
export type LibraryResult = {state: 'completed' | 'partial'; action: LibraryAction; count: number; deleted_files: number; message: string};
export function libraryBytes(value: number) {
  if (value < 1024) return `${value} B`;
  const scale = value >= 1024 ** 3 ? 3 : value >= 1024 ** 2 ? 2 : 1;
  return `${(value / 1024 ** scale).toFixed(1)} ${['B', 'KiB', 'MiB', 'GiB'][scale]}`;
}
export function libraryVisible(items: LibraryItem[], view: 'available' | 'trash', kind: string, query: string, sort: string) {
  const needle = query.trim().toLocaleLowerCase('ko');
  return items.filter(item => (view === 'available' ? item.state === 'available' : item.state !== 'available') &&
    (kind === 'all' || item.kind === kind) && `${item.title} ${item.name}`.toLocaleLowerCase('ko').includes(needle))
    .sort((a, b) => sort === 'size' ? b.size_bytes - a.size_bytes : b.modified_at.localeCompare(a.modified_at));
}
