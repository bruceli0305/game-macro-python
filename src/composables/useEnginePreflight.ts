import { DEFAULT_PROFILE_NAME, useProfile } from "./useProfile";
import { firstProfileError, validateProfileForEngineStart } from "../utils/profile-validation";

export function useEnginePreflight() {
  const { loadOrCreateProfile } = useProfile();

  async function validateEngineStart(): Promise<string | null> {
    const profile = await loadOrCreateProfile(DEFAULT_PROFILE_NAME);
    return firstProfileError(validateProfileForEngineStart(profile));
  }

  return { validateEngineStart };
}
