/**
 * useConversations — manages conversation list, active conversation,
 * new session, and restore. Extracted from App.jsx.
 */
import { useState, useCallback } from 'react';

export default function useConversations({ dispatch, discardStreamRef, isStreamingRef, setIsStreaming, setActiveTools }) {
  const [conversations, setConversations] = useState([]); // { id, title, time, messages[] }
  const [activeConvId, setActiveConvId] = useState(null);

  /** Called when user sends a message — auto-titles the first message. */
  const autoTitle = useCallback((text, currentMsgCount) => {
    if (currentMsgCount === 0 && !activeConvId) {
      const id = Date.now().toString();
      const title = text.slice(0, 40) + (text.length > 40 ? '...' : '');
      setActiveConvId(id);
      setConversations(prev => [{ id, title, time: new Date().toLocaleTimeString(), messages: [] }, ...prev]);
      return id;
    }
    return null;
  }, [activeConvId]);

  /** Sync latest messages into the active conversation entry. */
  const syncMessages = useCallback((messages) => {
    if (activeConvId && messages.length > 0) {
      setConversations(prev => prev.map(c =>
        c.id === activeConvId ? { ...c, messages } : c
      ));
    }
  }, [activeConvId]);

  /** Click on a past conversation — restore its messages. */
  const selectConv = useCallback((convId) => {
    if (convId === activeConvId) return;
    const conv = conversations.find(c => c.id === convId);
    if (!conv?.messages?.length) return;
    discardStreamRef.current = true;
    isStreamingRef.current = false;
    setIsStreaming(false);
    setActiveTools([]);
    setActiveConvId(convId);
    dispatch({ type: 'RESTORE_MESSAGES', messages: conv.messages });
  }, [activeConvId, conversations, dispatch, discardStreamRef, isStreamingRef, setIsStreaming, setActiveTools]);

  /** Start a blank session without losing history. */
  const newSession = useCallback((extraCleanup) => {
    discardStreamRef.current = true;
    dispatch({ type: 'CLEAR' });
    setActiveConvId(null);
    setActiveTools([]);
    isStreamingRef.current = false;
    setIsStreaming(false);
    if (extraCleanup) extraCleanup();
  }, [dispatch, discardStreamRef, isStreamingRef, setIsStreaming, setActiveTools]);

  return { conversations, activeConvId, autoTitle, syncMessages, selectConv, newSession };
}
