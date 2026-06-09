import { useProfile } from "./useProfile";
import { firstProfileError, validateProfileForEngineStart } from "../utils/profile-validation";

export function useEnginePreflight() {
  const { loadActiveProfile } = useProfile();

  async function validateEngineStart(): Promise<string | null> {
    const profile = await loadActiveProfile();
    return firstProfileError(validateProfileForEngineStart(profile));
  }

  return { validateEngineStart };
}
