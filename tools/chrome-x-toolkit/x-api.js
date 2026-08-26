/**
 * X GraphQL / REST 客户端（使用页面登录态捕获的 Bearer + CSRF）
 */
/* global chrome */

const XApi = (() => {
  /** 常见 queryId 兜底（随 X 更新可能失效，优先用 inject 捕获的） */
  const DEFAULT_QUERY_IDS = {
    UserByScreenName: 'G3KGOASz96M-Qu0nwmFhNg',
    UserTweets: 'V7H0Ap3_Hh2xcaSQ8ZeePg',
    UserTweetsAndReplies: 'RIW0qY3yTqY82vRPC-grgQ',
    Likes: 'nXEl0lfN_XSznVMlprTyGmg',
    DeleteTweet: 'VaenaVgh5n5SjOirjxaphPmwUMedRl0yXryR_knEgd0',
    DeleteRetweet: 'i77LGYRky1dXHop96iNfEg',
    UnfavoriteTweet: 'ZYKSe-w7KEslx3_J8JsitQ',
  };

  const DEFAULT_FEATURES = {
    rweb_tipjar_consumption_enabled: true,
    responsive_web_graphql_exclude_directive_enabled: true,
    verified_phone_label_enabled: false,
    creator_subscriptions_tweet_preview_api_enabled: true,
    responsive_web_graphql_timeline_navigation_enabled: true,
    responsive_web_graphql_skip_user_profile_image_extensions_enabled: false,
    communities_web_enable_tweet_community_results_fetch: true,
    c9s_tweet_anatomy_moderator_badge_enabled: true,
    articles_preview_enabled: true,
    responsive_web_edit_tweet_api_enabled: true,
    graphql_is_translatable_rweb_tweet_is_translatable_enabled: true,
    view_counts_everywhere_api_enabled: true,
    longform_notetweets_consumption_enabled: true,
    responsive_web_twitter_article_tweet_consumption_enabled: true,
    tweet_awards_web_tipping_enabled: false,
    creator_subscriptions_quote_tweet_preview_enabled: false,
    freedom_of_speech_not_reach_fetch_enabled: true,
    standardized_nudges_misinfo: true,
    tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled: true,
    rweb_video_timestamps_enabled: true,
    longform_notetweets_rich_text_read_enabled: true,
    longform_notetweets_inline_media_enabled: true,
    responsive_web_enhance_cards_enabled: false,
  };

  let creds = { queryIds: { ...DEFAULT_QUERY_IDS } };

  function mergeCreds(patch) {
    if (!patch || typeof patch !== 'object') return creds;
    creds = {
      ...creds,
      ...patch,
      queryIds: { ...DEFAULT_QUERY_IDS, ...(creds.queryIds || {}), ...(patch.queryIds || {}) },
    };
    return creds;
  }

  function cookie(name) {
    const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return m ? decodeURIComponent(m[1]) : '';
  }

  function buildHeaders() {
    const csrf = creds.csrf || cookie('ct0');
    const auth = creds.authorization || '';
    if (!csrf) throw new Error('未捕获 CSRF（ct0），请在 X 上刷新页面并随意滚动一下');
    if (!auth.startsWith('Bearer')) {
      throw new Error('未捕获 Bearer Token，请确认已登录并在 X 上浏览几条时间线');
    }
    return {
      authorization: auth,
      'x-csrf-token': csrf,
      'x-twitter-auth-type': 'OAuth2Session',
      'x-twitter-active-user': 'yes',
      'x-twitter-client-language': 'zh-cn',
      'content-type': 'application/json',
      accept: '*/*',
    };
  }

  function queryId(op) {
    return (creds.queryIds && creds.queryIds[op]) || DEFAULT_QUERY_IDS[op];
  }

  async function graphql(op, variables, features) {
    const qid = queryId(op);
    if (!qid) throw new Error(`缺少 ${op} 的 queryId，请先在 X 上打开对应页面让插件捕获`);
    const url = `https://x.com/i/api/graphql/${qid}/${op}`;
    const resp = await fetch(url, {
      method: 'POST',
      headers: buildHeaders(),
      credentials: 'include',
      body: JSON.stringify({
        variables,
        features: features || DEFAULT_FEATURES,
        queryId: qid,
      }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const msg = data?.errors?.[0]?.message || data?.detail || resp.statusText;
      throw new Error(`${op} HTTP ${resp.status}: ${msg}`);
    }
    return data;
  }

  async function restGet(path) {
    const resp = await fetch(`https://x.com/i/api/1.1/${path}`, {
      headers: buildHeaders(),
      credentials: 'include',
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(`REST ${path} ${resp.status}`);
    return data;
  }

  async function getSelfProfile() {
    const data = await restGet('account/settings.json');
    return {
      userId: String(data.user_id_str || data.user_id || ''),
      screenName: data.screen_name || '',
      name: data.name || '',
    };
  }

  async function getUserIdByScreenName(screenName) {
    const sn = String(screenName || '').replace(/^@/, '').trim();
    if (!sn) throw new Error('缺少 screen_name');
    const data = await graphql('UserByScreenName', {
      screen_name: sn,
      withSafetyModeUserFields: true,
    });
    const uid = data?.data?.user?.result?.rest_id;
    if (!uid) throw new Error(`找不到用户 @${sn}`);
    return String(uid);
  }

  function parseTweetNode(node) {
    if (!node) return null;
    const r = node.tweet || node;
    const legacy = r.legacy || r.tweet?.legacy;
    if (!legacy) return null;
    const user = r.core?.user_results?.result?.legacy || r.user?.legacy || {};
    const id = r.rest_id || legacy.id_str;
    const isRetweet = Boolean(legacy.retweeted_status_result || legacy.retweeted_status);
    const rtLegacy = legacy.retweeted_status_result?.result?.legacy;
    return {
      id: String(id),
      createdAt: legacy.created_at,
      text: (legacy.full_text || '').slice(0, 280),
      userId: legacy.user_id_str,
      screenName: user.screen_name || '',
      isReply: Boolean(legacy.in_reply_to_status_id_str),
      isRetweet,
      retweetSourceId: rtLegacy?.id_str || legacy.retweeted_status_id_str || '',
      raw: r,
    };
  }

  function parseTimeline(data, op) {
    const instructions =
      data?.data?.user?.result?.timeline_v2?.timeline?.instructions ||
      data?.data?.user?.result?.timeline?.timeline?.instructions ||
      [];
    const items = [];
    let nextCursor = '';
    for (const ins of instructions) {
      if (ins.type === 'TimelineAddEntries') {
        for (const ent of ins.entries || []) {
          if (ent.content?.entryType === 'TimelineTimelineCursor' && ent.content?.cursorType === 'Bottom') {
            nextCursor = ent.content?.value || '';
          }
          const item = ent.content?.itemContent?.tweet_results?.result;
          const tw = parseTweetNode(item);
          if (tw) items.push(tw);
        }
      }
    }
    return { items, nextCursor, op };
  }

  async function fetchTimelinePage({ userId, cursor, mode }) {
    const opMap = {
      tweets: 'UserTweets',
      replies: 'UserTweetsAndReplies',
      likes: 'Likes',
    };
    const op = opMap[mode] || 'UserTweets';
    const variables = {
      userId,
      count: 40,
      includePromotedContent: false,
      withQuickPromoteEligibilityTweetFields: true,
      withVoice: true,
    };
    if (cursor) variables.cursor = cursor;
    const data = await graphql(op, variables);
    return parseTimeline(data, op);
  }

  async function* iterateTimeline({ userId, mode, maxPages = 80 }) {
    let cursor = '';
    for (let p = 0; p < maxPages; p++) {
      const page = await fetchTimelinePage({ userId, cursor, mode });
      yield page;
      if (!page.nextCursor || page.nextCursor === cursor) break;
      cursor = page.nextCursor;
      await sleep(800);
    }
  }

  async function deleteTweet(tweetId) {
    return graphql('DeleteTweet', { tweet_id: tweetId, dark_request: false });
  }

  async function deleteRetweet(sourceTweetId) {
    return graphql('DeleteRetweet', { source_tweet_id: sourceTweetId, dark_request: false });
  }

  async function unlike(tweetId) {
    return graphql('UnfavoriteTweet', { tweet_id: tweetId });
  }

  function parseDate(s) {
    if (!s) return null;
    const d = new Date(s);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function inDateRange(isoOrTwitterDate, start, end) {
    const d = parseDate(isoOrTwitterDate);
    if (!d) return false;
    const t = d.getTime();
    return t >= start.getTime() && t <= end.getTime();
  }

  async function collectForCleanup({ userId, startDate, endDate, types, onProgress }) {
    const start = new Date(startDate + 'T00:00:00');
    const end = new Date(endDate + 'T23:59:59');
    const out = [];
    const seen = new Set();

    const modes = [];
    if (types.posts || types.replies) modes.push({ mode: 'replies', needReply: types.replies, needPost: types.posts });
    if (types.posts && !types.replies) modes.push({ mode: 'tweets', needReply: false, needPost: true });
    if (types.likes) modes.push({ mode: 'likes', needReply: false, needPost: false, isLike: true });
    if (types.retweets) modes.push({ mode: 'tweets', needReply: false, needPost: false, retweetsOnly: true });

    for (const cfg of modes) {
      onProgress?.(`扫描 ${cfg.mode}…`);
      let stale = 0;
      for await (const page of iterateTimeline({ userId, mode: cfg.mode })) {
        let hitInPage = 0;
        for (const tw of page.items) {
          if (!inDateRange(tw.createdAt, start, end)) {
            const d = parseDate(tw.createdAt);
            if (d && d < start) stale++;
            continue;
          }
          hitInPage++;
          let action = '';
          let targetId = tw.id;
          if (cfg.isLike) {
            action = 'unlike';
          } else if (cfg.retweetsOnly) {
            if (!tw.isRetweet) continue;
            action = 'unretweet';
            targetId = tw.retweetSourceId || tw.id;
          } else if (tw.isRetweet && types.retweets) {
            action = 'unretweet';
            targetId = tw.retweetSourceId || tw.id;
          } else if (tw.isReply && cfg.needReply) {
            action = 'delete';
          } else if (!tw.isReply && !tw.isRetweet && cfg.needPost) {
            action = 'delete';
          } else {
            continue;
          }
          const key = `${action}:${targetId}`;
          if (seen.has(key)) continue;
          seen.add(key);
          out.push({
            action,
            tweetId: targetId,
            displayId: tw.id,
            createdAt: tw.createdAt,
            text: tw.text,
            kind: action === 'unlike' ? 'like' : action === 'unretweet' ? 'retweet' : tw.isReply ? 'reply' : 'post',
          });
        }
        onProgress?.(`${cfg.mode} 已收集 ${out.length} 条…`);
        if (stale > 3 && hitInPage === 0) break;
        if (hitInPage === 0) stale++;
        else stale = 0;
      }
    }
    return out.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
  }

  async function runCleanup(items, { delayMs = 1200, onItem, shouldStop }) {
    const results = { ok: 0, fail: 0, errors: [] };
    for (let i = 0; i < items.length; i++) {
      if (shouldStop?.()) break;
      const it = items[i];
      onItem?.({ index: i + 1, total: items.length, item: it, phase: 'running' });
      try {
        if (it.action === 'delete') await deleteTweet(it.tweetId);
        else if (it.action === 'unretweet') await deleteRetweet(it.tweetId);
        else if (it.action === 'unlike') await unlike(it.tweetId);
        results.ok++;
        onItem?.({ index: i + 1, total: items.length, item: it, phase: 'done' });
      } catch (e) {
        results.fail++;
        results.errors.push({ item: it, error: String(e.message || e) });
        onItem?.({ index: i + 1, total: items.length, item: it, phase: 'error', error: String(e.message || e) });
      }
      await sleep(delayMs);
    }
    return results;
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  return {
    mergeCreds,
    getSelfProfile,
    getUserIdByScreenName,
    collectForCleanup,
    runCleanup,
    deleteTweet,
    deleteRetweet,
    unlike,
    get creds() {
      return creds;
    },
  };
})();

if (typeof window !== 'undefined') window.XApi = XApi;
