/**
 * 加载剧本内可选角色（配音幕角色选择）。
 */

import { useCallback, useEffect, useState } from "react";
import {
  fetchCharacterBoardOptions,
  type CharacterBoardOption,
} from "../utils/shotCharacterBoard";

/** 拉取当前剧本角色列表，供配音幕选择旁白或已有角色。 */
export function useVoiceActCharacters(projectId: string | null | undefined, scriptId: string | null | undefined) {
  const [characters, setCharacters] = useState<CharacterBoardOption[]>([]);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(async () => {
    if (!projectId || !scriptId) {
      setCharacters([]);
      return;
    }
    setLoading(true);
    try {
      setCharacters(await fetchCharacterBoardOptions(projectId, scriptId));
    } finally {
      setLoading(false);
    }
  }, [projectId, scriptId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { characters, loading, reload };
}
