import { describe, expect, it } from 'vitest';
import { mockPatients } from '@/lib/mock/data';

describe('mockPatients', () => {
  it('keeps every demo patient older than 60', () => {
    expect(mockPatients.length).toBeGreaterThan(0);
    expect(mockPatients.every((patient) => patient.age > 60)).toBe(true);
  });
});
