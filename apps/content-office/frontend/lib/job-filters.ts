import type { JobMetadata } from './types';

const normalize = (value: string) => value.normalize('NFKC').toLocaleLowerCase('ko-KR').replace(/\s+/g, ' ').trim();

export function jobFilterStates(jobs: JobMetadata[], selected: string) {
  return [...new Set([...jobs.map(job => job.state), ...(selected === 'all' ? [] : [selected])])].sort();
}

export function filterJobs(jobs: JobMetadata[], query: string, state: string, output: string) {
  const text = normalize(query);
  return jobs.filter(job => (!text || normalize(`${job.title} ${job.id}`).includes(text)) &&
    (state === 'all' || job.state === state) &&
    (output === 'all' || (output === 'unspecified' ? !job.output_kinds?.length : job.output_kinds?.includes(output))));
}
