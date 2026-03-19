import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { LicenseStatus, AppSettings } from "./api";

interface AppState {
  licenseStatus: LicenseStatus | null;
  settings: AppSettings | null;
  activeBookId: string | null;
  setLicenseStatus: (s: LicenseStatus) => void;
  setSettings: (s: AppSettings) => void;
  setActiveBookId: (id: string | null) => void;
  clearLicense: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      licenseStatus: null,
      settings: null,
      activeBookId: null,
      setLicenseStatus: (s) => set({ licenseStatus: s }),
      setSettings: (s) => set({ settings: s }),
      setActiveBookId: (id) => set({ activeBookId: id }),
      clearLicense: () => set({ licenseStatus: null }),
    }),
    {
      name: "bookengine-app-state",
      partialize: (state) => ({
        licenseStatus: state.licenseStatus,
        activeBookId: state.activeBookId,
      }),
    }
  )
);
