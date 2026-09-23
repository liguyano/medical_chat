import { describe, expect, it } from 'vitest';
import { patientDemoAccounts } from '@/lib/patient/demoAccounts';

describe('patientDemoAccounts', () => {
  it('keeps every linked demo identity older than 60', () => {
    const today = new Date();

    for (const account of patientDemoAccounts) {
      const birthdayText = account.idCardNo.slice(6, 14);
      const birthday = new Date(
        Number(birthdayText.slice(0, 4)),
        Number(birthdayText.slice(4, 6)) - 1,
        Number(birthdayText.slice(6, 8)),
      );
      const age = today.getFullYear() - birthday.getFullYear() - (
        today.getMonth() < birthday.getMonth()
        || (today.getMonth() === birthday.getMonth() && today.getDate() < birthday.getDate())
          ? 1
          : 0
      );

      expect(age, account.name).toBeGreaterThan(60);
    }
  });
});