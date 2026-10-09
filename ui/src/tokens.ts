export const TOKENS = {
  canvas: '#0C111B',
  panel: '#121A27',
  raised: '#1A2535',
  border: '#2B384B',
  textPrimary: '#EDF2FA',
  textSecondary: '#ACBBCE',
  teal: '#63DFD0', // interactive / provenance
  success: '#87E2AF',
  review: '#F3C47E',
  error: '#FF8795',
  darkInk: '#0C111B',
} as const;

export type ColorToken = keyof typeof TOKENS;
