import { useMemo } from "react";
import type { ApplicationRoleAssignment, CurrentUser } from "@/api/authApi";
import { useAuth } from "./authContext";

/**
 * Access-control helpers (doc 01 §2). The backend enforces every rule; the UI only hides what a user cannot do.
 * `isKeiganAdmin` can read and edit every application.
 */

export function canReadApplication(user: CurrentUser | null, applicationId: string): boolean {
  if (!user) return false;
  return user.isKeiganAdmin || user.applicationRoles.some((assignment) => assignment.applicationId === applicationId);
}

export function canEditApplication(user: CurrentUser | null, applicationId: string): boolean {
  if (!user) return false;
  return user.isKeiganAdmin || user.applicationRoles.some((assignment) => assignment.applicationId === applicationId && assignment.role === "admin");
}

/** True when the user belongs to no application and is not a Keigan admin ("request access" state). */
export function hasNoAccess(user: CurrentUser | null): boolean {
  return !!user && !user.isKeiganAdmin && user.applicationRoles.length === 0;
}

export type HighestRole = "keiganAdmin" | "applicationAdmin" | "reader" | "noAccess";

export function highestRoleOf(user: CurrentUser): HighestRole {
  if (user.isKeiganAdmin) return "keiganAdmin";
  if (user.applicationRoles.some((assignment) => assignment.role === "admin")) return "applicationAdmin";
  return user.applicationRoles.length > 0 ? "reader" : "noAccess";
}

export interface AccessControl {
  user: CurrentUser | null;
  isKeiganAdmin: boolean;
  /** Applications from the user's role assignments (a Keigan admin may see more through `GET /applications`). */
  roleAssignments: ApplicationRoleAssignment[];
  canRead: (applicationId: string) => boolean;
  canEdit: (applicationId: string) => boolean;
  highestRole: HighestRole | null;
}

/** `const { isKeiganAdmin, canEdit } = useAccessControl();` then `canEdit(applicationId)`. */
export function useAccessControl(): AccessControl {
  const { user } = useAuth();
  return useMemo<AccessControl>(
    () => ({
      user,
      isKeiganAdmin: user?.isKeiganAdmin === true,
      roleAssignments: user?.applicationRoles ?? [],
      canRead: (applicationId) => canReadApplication(user, applicationId),
      canEdit: (applicationId) => canEditApplication(user, applicationId),
      highestRole: user ? highestRoleOf(user) : null,
    }),
    [user],
  );
}
