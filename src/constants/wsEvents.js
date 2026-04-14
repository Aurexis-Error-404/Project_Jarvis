// src/constants/wsEvents.js — WebSocket event name registry
// Single source of truth for all event strings shared between frontend and backend.
// Outbound: events the frontend sends to the backend.
// Inbound:  events the backend sends to the frontend.

export const SEND = {
  USER_QUERY:        'user_query',
  MODE_CHANGE:       'mode_change',
  SURFACE_DISMISSED: 'surface_dismissed',
  SET_PROJECT_PATH:  'set_project_path',
  DEMO_SURFACE:      'demo_surface',
};

export const RECV = {
  STREAM_CHUNK:     'jarvis_stream_chunk',
  SURFACE:          'jarvis_surface',
  MODE_ACK:         'jarvis_mode_ack',
  ERROR:            'jarvis_error',
  STATUS_UPDATE:    'status_update',
  TOOL_CALL_STATUS: 'tool_call_status',
  REPORT_GENERATED: 'report_generated',
  PROJECT_PATH_ACK: 'project_path_ack',
};
