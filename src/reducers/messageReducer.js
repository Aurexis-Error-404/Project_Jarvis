export default function messageReducer(state, action) {
  switch (action.type) {
    case 'ADD_USER_MESSAGE':
      return [...state, { id: Date.now(), role: 'user', text: action.text, timestamp: new Date() }];
    case 'ADD_JARVIS_MESSAGE':
      return [...state, { id: Date.now(), role: 'jarvis', text: action.text, timestamp: new Date() }];
    case 'START_STREAM':
      return [...state, { id: action.id || Date.now(), role: 'jarvis', text: '', timestamp: new Date(), streaming: true }];
    case 'APPEND_CHUNK':
      return state.map((msg, i) => i === state.length - 1 && msg.streaming ? { ...msg, text: msg.text + action.text } : msg);
    case 'FINISH_STREAM': {
      const last = state[state.length - 1];
      if (last?.streaming && !last.text) return state.slice(0, -1);
      return state.map((msg, i) => i === state.length - 1 && msg.streaming ? { ...msg, streaming: false } : msg);
    }
    case 'REPLACE_RESPONSE':
      return state.map((msg, i) => i === state.length - 1 && msg.role === 'jarvis' ? { ...msg, text: action.text, streaming: false } : msg);
    case 'ADD_ERROR':
      return [...state, { id: Date.now(), role: 'error', text: action.message, timestamp: new Date() }];
    case 'CLEAR':
      return [];
    default:
      return state;
  }
}
