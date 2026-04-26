"use client";

import {
  createContext,
  PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { workflowSections, WorkflowSectionId } from "@/lib/workflow-sections";

type SectionRegistryContextValue = {
  activeSectionId: WorkflowSectionId;
  navigationLocked: boolean;
  setNavigationLocked: (locked: boolean) => void;
  registerSection: (id: WorkflowSectionId, element: HTMLElement | null) => void;
  registerScrollContainer: (
    id: WorkflowSectionId,
    element: HTMLElement | null
  ) => void;
  scrollToSection: (id: WorkflowSectionId) => void;
  goNextSection: () => void;
  goPrevSection: () => void;
  goActiveSectionDown: () => void;
  canExitSectionDown: (id: WorkflowSectionId) => boolean;
  canExitSectionUp: (id: WorkflowSectionId) => boolean;
  canAdvanceWithinSection: (id: WorkflowSectionId) => boolean;
  hasNextSection: boolean;
};

const SectionRegistryContext = createContext<SectionRegistryContextValue | null>(null);

function resolveNavHeight() {
  const rootStyles = window.getComputedStyle(document.documentElement);
  const rawValue = rootStyles.getPropertyValue("--nav-height").trim();

  if (!rawValue) {
    return 88;
  }

  if (rawValue.endsWith("px")) {
    const parsed = Number.parseFloat(rawValue);
    return Number.isFinite(parsed) ? parsed : 88;
  }

  if (rawValue.endsWith("rem")) {
    const rootFontSize = Number.parseFloat(rootStyles.fontSize || "16");
    const remValue = Number.parseFloat(rawValue);
    if (Number.isFinite(rootFontSize) && Number.isFinite(remValue)) {
      return rootFontSize * remValue;
    }
  }

  const parsed = Number.parseFloat(rawValue);
  return Number.isFinite(parsed) ? parsed : 88;
}

export function SectionRegistryProvider({ children }: PropsWithChildren) {
  const [activeSectionId, setActiveSectionId] = useState<WorkflowSectionId>("main");
  const [navigationLocked, setNavigationLocked] = useState(false);
  const [sectionElements, setSectionElements] = useState<
    Partial<Record<WorkflowSectionId, HTMLElement | null>>
  >({});
  const [scrollContainers, setScrollContainers] = useState<
    Partial<Record<WorkflowSectionId, HTMLElement | null>>
  >({});
  const sectionElementsRef = useRef(sectionElements);
  const scrollContainersRef = useRef(scrollContainers);
  const rememberedScrollPositionsRef = useRef<
    Partial<Record<WorkflowSectionId, number>>
  >({});
  const activeSectionIdRef = useRef(activeSectionId);
  const navigationLockedRef = useRef(navigationLocked);
  const transitionLockRef = useRef(false);
  const transitionLockTimeoutRef = useRef<number | null>(null);
  const intentAccumulatorRef = useRef(0);
  const lastDirectionRef = useRef<1 | -1 | 0>(0);
  const intentResetTimeoutRef = useRef<number | null>(null);
  const isDesktopRef = useRef(false);

  useEffect(() => {
    sectionElementsRef.current = sectionElements;
  }, [sectionElements]);

  useEffect(() => {
    scrollContainersRef.current = scrollContainers;
  }, [scrollContainers]);

  useEffect(() => {
    activeSectionIdRef.current = activeSectionId;
  }, [activeSectionId]);

  useEffect(() => {
    navigationLockedRef.current = navigationLocked;
  }, [navigationLocked]);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(min-width: 1024px)");

    const updateDesktopMode = () => {
      isDesktopRef.current = mediaQuery.matches;
    };

    updateDesktopMode();

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", updateDesktopMode);
      return () => mediaQuery.removeEventListener("change", updateDesktopMode);
    }

    mediaQuery.addListener(updateDesktopMode);
    return () => mediaQuery.removeListener(updateDesktopMode);
  }, []);

  const registerSection = useCallback(
    (id: WorkflowSectionId, element: HTMLElement | null) => {
      setSectionElements((current) => {
        if (current[id] === element) {
          return current;
        }

        return {
          ...current,
          [id]: element,
        };
      });
    },
    []
  );

  const registerScrollContainer = useCallback(
    (id: WorkflowSectionId, element: HTMLElement | null) => {
      if (element) {
        const rememberedTop = rememberedScrollPositionsRef.current[id];
        if (typeof rememberedTop === "number") {
          element.scrollTop = rememberedTop;
        }
      }

      setScrollContainers((current) => {
        if (current[id] === element) {
          return current;
        }

        return {
          ...current,
          [id]: element,
        };
      });
    },
    []
  );

  const canExitSectionDown = useCallback((id: WorkflowSectionId) => {
    if (!isDesktopRef.current) {
      return true;
    }
    const container = scrollContainersRef.current[id];
    if (!container) {
      return true;
    }

    return (
      container.scrollTop + container.clientHeight >=
      container.scrollHeight - 2
    );
  }, []);

  const canExitSectionUp = useCallback((id: WorkflowSectionId) => {
    if (!isDesktopRef.current) {
      return true;
    }
    const container = scrollContainersRef.current[id];
    if (!container) {
      return true;
    }

    return container.scrollTop <= 2;
  }, []);

  const clearIntentAccumulator = useCallback(() => {
    intentAccumulatorRef.current = 0;
    lastDirectionRef.current = 0;
    if (intentResetTimeoutRef.current !== null) {
      window.clearTimeout(intentResetTimeoutRef.current);
      intentResetTimeoutRef.current = null;
    }
  }, []);

  const lockTransitions = useCallback(() => {
    transitionLockRef.current = true;
    if (transitionLockTimeoutRef.current !== null) {
      window.clearTimeout(transitionLockTimeoutRef.current);
    }
    transitionLockTimeoutRef.current = window.setTimeout(() => {
      transitionLockRef.current = false;
    }, 850);
  }, []);

  const getSectionIndex = useCallback(
    (id: WorkflowSectionId) =>
      workflowSections.findIndex((section) => section.id === id),
    []
  );

  const canAdvanceWithinSection = useCallback((id: WorkflowSectionId) => {
    if (!isDesktopRef.current) {
      return false;
    }
    const container = scrollContainersRef.current[id];
    if (!container) {
      return false;
    }

    return container.scrollTop + container.clientHeight < container.scrollHeight - 2;
  }, []);

  useEffect(() => {
    const handleScroll = () => {
      const navHeight = resolveNavHeight();
      const viewportAnchor = window.scrollY + navHeight + 20;

      let nearestId = activeSectionIdRef.current;
      let smallestDistance = Number.POSITIVE_INFINITY;

      workflowSections.forEach(({ id }) => {
        const element = sectionElementsRef.current[id];
        if (!element) {
          return;
        }

        const distance = Math.abs(element.offsetTop - viewportAnchor);
        if (distance < smallestDistance) {
          smallestDistance = distance;
          nearestId = id;
        }
      });

      if (nearestId !== activeSectionIdRef.current) {
        setActiveSectionId(nearestId);
      }
    };

    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });

    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const scrollToSection = useCallback((id: WorkflowSectionId) => {
    if (navigationLockedRef.current) {
      return;
    }

    const currentSectionId = activeSectionIdRef.current;
    const currentScrollContainer = scrollContainersRef.current[currentSectionId];
    if (currentScrollContainer) {
      rememberedScrollPositionsRef.current[currentSectionId] =
        currentScrollContainer.scrollTop;
    }

    const element = sectionElementsRef.current[id];
    if (!element) {
      return;
    }
    const scrollContainer = scrollContainersRef.current[id];

    const navHeight = resolveNavHeight();
    const top = element.getBoundingClientRect().top + window.scrollY - navHeight - (isDesktopRef.current ? 0 : 12);

    if (scrollContainer) {
      scrollContainer.scrollTo({
        top: 0,
        behavior: "auto",
      });
      rememberedScrollPositionsRef.current[id] = 0;
    }

    window.scrollTo({
      top,
      behavior: "smooth",
    });
    setActiveSectionId(id);
    clearIntentAccumulator();
    lockTransitions();
  }, [clearIntentAccumulator, lockTransitions]);

  const goNextSection = useCallback(() => {
    if (navigationLockedRef.current) {
      return;
    }
    const currentIndex = getSectionIndex(activeSectionIdRef.current);
    const nextSection = workflowSections[currentIndex + 1];
    if (!nextSection) {
      return;
    }
    scrollToSection(nextSection.id);
  }, [getSectionIndex, scrollToSection]);

  const goPrevSection = useCallback(() => {
    if (navigationLockedRef.current) {
      return;
    }
    const currentIndex = getSectionIndex(activeSectionIdRef.current);
    const previousSection = workflowSections[currentIndex - 1];
    if (!previousSection) {
      return;
    }
    scrollToSection(previousSection.id);
  }, [getSectionIndex, scrollToSection]);

  const goActiveSectionDown = useCallback(() => {
    const currentSectionId = activeSectionIdRef.current;
    const scrollContainer = scrollContainersRef.current[currentSectionId];

    if (scrollContainer && canAdvanceWithinSection(currentSectionId)) {
      const delta = Math.max(scrollContainer.clientHeight * 0.8, 280);
      scrollContainer.scrollBy({
        top: delta,
        behavior: "smooth",
      });
      clearIntentAccumulator();
      return;
    }

    if (navigationLockedRef.current) {
      return;
    }

    goNextSection();
  }, [canAdvanceWithinSection, clearIntentAccumulator, goNextSection]);

  useEffect(() => {
    const handleWheel = (event: WheelEvent) => {
      const currentSectionId = activeSectionIdRef.current;
      const deltaY = event.deltaY;

      if (deltaY === 0) {
        return;
      }

      if (!isDesktopRef.current) {
        return;
      }

      if (transitionLockRef.current) {
        event.preventDefault();
        return;
      }

      const direction: 1 | -1 = deltaY > 0 ? 1 : -1;
      const scrollContainer = scrollContainersRef.current[currentSectionId];

      if (scrollContainer) {
        const canScrollDown =
          scrollContainer.scrollTop + scrollContainer.clientHeight <
          scrollContainer.scrollHeight - 2;
        const canScrollUp = scrollContainer.scrollTop > 2;

        if ((direction > 0 && canScrollDown) || (direction < 0 && canScrollUp)) {
          event.preventDefault();
          scrollContainer.scrollTop += deltaY;
          clearIntentAccumulator();
          return;
        }
      }

      if (navigationLockedRef.current) {
        event.preventDefault();
        return;
      }

      const canExit =
        direction > 0
          ? canExitSectionDown(currentSectionId)
          : canExitSectionUp(currentSectionId);

      if (!canExit) {
        return;
      }

      event.preventDefault();

      if (lastDirectionRef.current !== direction) {
        intentAccumulatorRef.current = 0;
      }

      lastDirectionRef.current = direction;
      intentAccumulatorRef.current += Math.abs(deltaY);

      if (intentResetTimeoutRef.current !== null) {
        window.clearTimeout(intentResetTimeoutRef.current);
      }

      intentResetTimeoutRef.current = window.setTimeout(() => {
        clearIntentAccumulator();
      }, 240);

      if (intentAccumulatorRef.current < 180) {
        return;
      }

      clearIntentAccumulator();

      if (direction > 0) {
        goNextSection();
      } else {
        goPrevSection();
      }
    };

    window.addEventListener("wheel", handleWheel, { passive: false });

    return () => {
      window.removeEventListener("wheel", handleWheel);
      if (transitionLockTimeoutRef.current !== null) {
        window.clearTimeout(transitionLockTimeoutRef.current);
      }
      if (intentResetTimeoutRef.current !== null) {
        window.clearTimeout(intentResetTimeoutRef.current);
      }
    };
  }, [
    canExitSectionDown,
    canExitSectionUp,
    clearIntentAccumulator,
    goNextSection,
    goPrevSection,
  ]);

  const value = useMemo(
    () => ({
      activeSectionId,
      navigationLocked,
      setNavigationLocked,
      registerSection,
      registerScrollContainer,
      scrollToSection,
      goNextSection,
      goPrevSection,
      goActiveSectionDown,
      canExitSectionDown,
      canExitSectionUp,
      canAdvanceWithinSection,
      hasNextSection:
        getSectionIndex(activeSectionId) < workflowSections.length - 1,
    }),
    [
      activeSectionId,
      navigationLocked,
      canAdvanceWithinSection,
      canExitSectionDown,
      canExitSectionUp,
      getSectionIndex,
      goActiveSectionDown,
      goNextSection,
      goPrevSection,
      registerScrollContainer,
      registerSection,
      setNavigationLocked,
      scrollToSection,
    ]
  );

  return (
    <SectionRegistryContext.Provider value={value}>
      {children}
    </SectionRegistryContext.Provider>
  );
}

export function useSectionRegistry() {
  const context = useContext(SectionRegistryContext);

  if (!context) {
    throw new Error(
      "useSectionRegistry must be used inside a SectionRegistryProvider."
    );
  }

  return context;
}
