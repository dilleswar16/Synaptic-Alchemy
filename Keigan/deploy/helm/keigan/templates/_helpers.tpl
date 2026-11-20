{{- define "keigan.labels" -}}
app.kubernetes.io/part-of: keigan
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "keigan.backendImage" -}}
{{ .Values.images.registry }}/{{ .Values.images.backend }}:{{ .Values.images.tag }}
{{- end -}}

{{- define "keigan.webImage" -}}
{{ .Values.images.registry }}/{{ .Values.images.web }}:{{ .Values.images.tag }}
{{- end -}}

{{- define "keigan.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: 10001
runAsGroup: 10001
fsGroup: 10001
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "keigan.containerSecurityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: ["ALL"]
{{- end -}}

{{- define "keigan.backendEnvironment" -}}
envFrom:
  - configMapRef:
      name: keigan-backend-configuration
{{- if .Values.keyVault.enabled }}
  - secretRef:
      name: keigan-backend-secrets
{{- end }}
{{- end -}}
