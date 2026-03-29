"use client";

import {
  createContext,
  PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { CanonicalStudy, createStudy, getStudyDetails, WorkflowReadiness } from "@/lib/api";

const LEGACY_LOCAL_STORAGE_KEY = "synthetic_responder_study_id";
const LAST_STUDY_LOCAL_STORAGE_KEY = "synthetic_responder_last_study_id";
const ACTIVE_STUDY_SESSION_STORAGE_KEY =
  "synthetic_responder_active_study_session_id";

type StudyContextValue = {
  studyId: string | null;
  study: CanonicalStudy | null;
  workflow: WorkflowReadiness | null | undefined;
  isCreatingStudy: boolean;
  isHydratingStudy: boolean;
  studyBootstrapError: string | null;
  createOrLoadStudy: () => Promise<string | null>;
  createFreshStudy: () => Promise<string | null>;
  refreshStudy: (targetStudyId?: string | null) => Promise<CanonicalStudy | null>;
  setStudy: (study: CanonicalStudy | null) => void;
};

const StudyContext = createContext<StudyContextValue | null>(null);

export function StudyProvider({ children }: PropsWithChildren) {
  const [studyId, setStudyId] = useState<string | null>(null);
  const [study, setStudyState] = useState<CanonicalStudy | null>(null);
  const [isCreatingStudy, setIsCreatingStudy] = useState(false);
  const [isHydratingStudy, setIsHydratingStudy] = useState(true);
  const [studyBootstrapError, setStudyBootstrapError] = useState<string | null>(
    null
  );

  const persistStudy = useCallback((nextStudy: CanonicalStudy | null) => {
    setStudyState(nextStudy);
    setStudyId(nextStudy?.study_id ?? null);

    if (typeof window === "undefined") {
      return;
    }

    if (nextStudy?.study_id) {
      window.sessionStorage.setItem(
        ACTIVE_STUDY_SESSION_STORAGE_KEY,
        nextStudy.study_id
      );
      window.localStorage.setItem(
        LAST_STUDY_LOCAL_STORAGE_KEY,
        nextStudy.study_id
      );
    } else {
      window.sessionStorage.removeItem(ACTIVE_STUDY_SESSION_STORAGE_KEY);
      window.localStorage.removeItem(LAST_STUDY_LOCAL_STORAGE_KEY);
    }
  }, []);

  const refreshStudy = useCallback(
    async (targetStudyId?: string | null) => {
      const resolvedStudyId = targetStudyId ?? studyId;

      if (!resolvedStudyId) {
        return null;
      }

      setIsHydratingStudy(true);
      try {
        const nextStudy = await getStudyDetails(resolvedStudyId);
        persistStudy(nextStudy);
        setStudyBootstrapError(null);
        return nextStudy;
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : "Unable to load the active study.";
        setStudyBootstrapError(message);
        return null;
      } finally {
        setIsHydratingStudy(false);
      }
    },
    [persistStudy, studyId]
  );

  const createNewStudy = useCallback(async () => {
    setIsCreatingStudy(true);

    try {
      const nextStudyId = await createStudy();
      const nextStudy = await getStudyDetails(nextStudyId);
      persistStudy(nextStudy);
      setStudyBootstrapError(null);
      return nextStudy;
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unable to create a study right now.";
      setStudyBootstrapError(message);
      return null;
    } finally {
      setIsCreatingStudy(false);
      setIsHydratingStudy(false);
    }
  }, [persistStudy]);

  const createOrLoadStudy = useCallback(async () => {
    if (study?.study_id) {
      return study.study_id;
    }

    if (studyId) {
      const existingStudy = await refreshStudy(studyId);
      if (existingStudy?.study_id) {
        return existingStudy.study_id;
      }
    }

    const createdStudy = await createNewStudy();
    return createdStudy?.study_id ?? null;
  }, [createNewStudy, refreshStudy, study, studyId]);

  const createFreshStudy = useCallback(async () => {
    const createdStudy = await createNewStudy();
    return createdStudy?.study_id ?? null;
  }, [createNewStudy]);

  useEffect(() => {
    let cancelled = false;

    async function bootstrapStudy() {
      if (typeof window === "undefined") {
        return;
      }

      window.localStorage.removeItem(LEGACY_LOCAL_STORAGE_KEY);

      const savedStudyId = window.sessionStorage.getItem(
        ACTIVE_STUDY_SESSION_STORAGE_KEY
      );

      if (savedStudyId) {
        setIsHydratingStudy(true);
        try {
          const restoredStudy = await getStudyDetails(savedStudyId);
          if (!cancelled) {
            persistStudy(restoredStudy);
            setStudyBootstrapError(null);
            setIsHydratingStudy(false);
          }
          return;
        } catch {
          window.sessionStorage.removeItem(ACTIVE_STUDY_SESSION_STORAGE_KEY);
          if (!cancelled) {
            persistStudy(null);
          }
        }
      }

      if (!cancelled) {
        await createNewStudy();
      }
    }

    void bootstrapStudy();

    return () => {
      cancelled = true;
    };
  }, [createNewStudy, persistStudy]);

  const setStudy = useCallback(
    (nextStudy: CanonicalStudy | null) => {
      persistStudy(nextStudy);
      if (nextStudy) {
        setStudyBootstrapError(null);
      }
    },
    [persistStudy]
  );

  const value = useMemo(
    () => ({
      studyId,
      study,
      workflow: study?.derived?.workflow,
      isCreatingStudy,
      isHydratingStudy,
      studyBootstrapError,
      createOrLoadStudy,
      createFreshStudy,
      refreshStudy,
      setStudy,
    }),
    [
      createOrLoadStudy,
      createFreshStudy,
      isCreatingStudy,
      isHydratingStudy,
      refreshStudy,
      setStudy,
      study,
      studyBootstrapError,
      studyId,
    ]
  );

  return <StudyContext.Provider value={value}>{children}</StudyContext.Provider>;
}

export function useStudy() {
  const context = useContext(StudyContext);

  if (!context) {
    throw new Error("useStudy must be used inside a StudyProvider.");
  }

  return context;
}
