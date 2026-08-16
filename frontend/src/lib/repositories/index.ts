import { runtimeConfig, type DataMode } from '@/lib/runtime/config';
import { ApiCareRepository } from '@/lib/repositories/apiRepository';
import { MockCareRepository } from '@/lib/repositories/mockRepository';
import type { CareRepository } from '@/lib/repositories/types';

const repositories: Record<DataMode, CareRepository> = {
  mock: new MockCareRepository(),
  api: new ApiCareRepository(),
};

export function getCareRepository(
  mode: DataMode = runtimeConfig.dataMode
): CareRepository {
  return repositories[mode];
}

export const careRepository = getCareRepository();
