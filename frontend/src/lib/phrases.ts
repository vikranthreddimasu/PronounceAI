import type { Phrase } from "./types";

export const PHRASES: Phrase[] = [
  // Minimal pairs — 10
  { id: "mp-01", text: "I can't tell if you want the ship or the sheep on this map.", focus: "ɪ-vs-iː", category: "minimal-pair" },
  { id: "mp-02", text: "This is a thin thing, but I'm thankful for it anyway.", focus: "ð-vs-θ", category: "minimal-pair" },
  { id: "mp-03", text: "The right light is bright enough to read by all night.", focus: "r-vs-l", category: "minimal-pair" },
  { id: "mp-04", text: "I made three free throws before the buzzer sounded.", focus: "θ-vs-f", category: "minimal-pair" },
  { id: "mp-05", text: "I packed a bag in my bed, then ran back to grab it again.", focus: "ɛ-vs-æ", category: "minimal-pair" },
  { id: "mp-06", text: "Pull the pool cover off and we'll be full of food before noon.", focus: "ʊ-vs-uː", category: "minimal-pair" },
  { id: "mp-07", text: "I lost my hat in the hot wind, but I made it back from that great height before the date.", focus: "vowel-contrasts", category: "minimal-pair" },
  { id: "mp-08", text: "We will visit the vineyard when the white van finally leaves.", focus: "w-vs-v", category: "minimal-pair" },
  { id: "mp-09", text: "She saw zebras grazing as the sun set behind the lake.", focus: "s-vs-z", category: "minimal-pair" },
  { id: "mp-10", text: "The fat bat patted the mat where my poor vase had landed.", focus: "initial-consonants", category: "minimal-pair" },

  // Phoneme drills — 15
  { id: "pd-01", text: "The weather is rather better together than it was yesterday.", focus: "ð-medial", category: "phoneme-drill" },
  { id: "pd-02", text: "Thirty-three thousand thunderstorms rolled across the prairie.", focus: "θ-initial", category: "phoneme-drill" },
  { id: "pd-03", text: "A red lorry overtook a yellow lorry on the curving road.", focus: "r-l-cluster", category: "phoneme-drill" },
  { id: "pd-04", text: "She sells seashells by the seashore every summer morning.", focus: "ʃ-vs-s", category: "phoneme-drill" },
  { id: "pd-05", text: "The world's worst worker said the work was worth doing well.", focus: "ɜː-vowel", category: "phoneme-drill" },
  { id: "pd-06", text: "I watched a very vivid video about a vanishing village.", focus: "v-initial", category: "phoneme-drill" },
  { id: "pd-07", text: "I want to wash the car and watch the water before I walk to work.", focus: "w-ɒ-cluster", category: "phoneme-drill" },
  { id: "pd-08", text: "The butter is better in the batter when the bottle is bigger.", focus: "flap-t", category: "phoneme-drill" },
  { id: "pd-09", text: "The bridge has remarkable strength despite its narrow length.", focus: "consonant-cluster", category: "phoneme-drill" },
  { id: "pd-10", text: "We hiked around the rough and rugged rock at sunrise.", focus: "r-color", category: "phoneme-drill" },
  { id: "pd-11", text: "Huge humid winds blew through the human-shaped hedges all afternoon.", focus: "hjuː-onset", category: "phoneme-drill" },
  { id: "pd-12", text: "Which witch switched which switch on the haunted wall?", focus: "wh-vs-w", category: "phoneme-drill" },
  { id: "pd-13", text: "Autumn often offers the office a warm orange morning light.", focus: "ɒ-vs-ɔː", category: "phoneme-drill" },
  { id: "pd-14", text: "The angel changed her dangerous strategy at a strangely young age.", focus: "dʒ-medial", category: "phoneme-drill" },
  { id: "pd-15", text: "I thought thirty thick threads would be enough to fix this thing.", focus: "θ-cluster", category: "phoneme-drill" },

  // Connected speech / prosody — 15
  { id: "cs-01", text: "Can you give me a hand with this box for a second?", focus: "weak-forms", category: "connected-speech" },
  { id: "cs-02", text: "I should have told you about it sooner, I'm sorry.", focus: "should-have-reduction", category: "connected-speech" },
  { id: "cs-03", text: "What do you want to do tonight after the meeting wraps up?", focus: "wanna-gonna", category: "connected-speech" },
  { id: "cs-04", text: "It's only a matter of time before this whole thing falls apart.", focus: "stress-timing", category: "connected-speech" },
  { id: "cs-05", text: "The data really doesn't support that conclusion at all.", focus: "stress-placement", category: "connected-speech" },
  { id: "cs-06", text: "I wouldn't have gone if I had known what was waiting for me.", focus: "conditional-reduction", category: "connected-speech" },
  { id: "cs-07", text: "We're going to need a bigger boat for tomorrow's trip.", focus: "gonna-linking", category: "connected-speech" },
  { id: "cs-08", text: "Is there anything at all I can do to help out tonight?", focus: "intonation-rise", category: "connected-speech" },
  { id: "cs-09", text: "She asked him whether he'd already eaten before the show.", focus: "reported-speech-rhythm", category: "connected-speech" },
  { id: "cs-10", text: "The quick brown fox jumps over the lazy dog before lunch.", focus: "full-prosody", category: "connected-speech" },
  { id: "cs-11", text: "You know what I mean, right? It's not a difficult question.", focus: "discourse-markers", category: "connected-speech" },
  { id: "cs-12", text: "I've been waiting here for nearly an hour and no one came.", focus: "present-perfect-stress", category: "connected-speech" },
  { id: "cs-13", text: "Could you possibly speak a little more slowly for me, please?", focus: "polite-intonation", category: "connected-speech" },
  { id: "cs-14", text: "Honestly, I have absolutely no idea what they were thinking.", focus: "emphatic-stress", category: "connected-speech" },
  { id: "cs-15", text: "Let me know if you need anything at all before you leave.", focus: "falling-intonation", category: "connected-speech" },

  // Authentic — 10
  { id: "au-01", text: "To be, or not to be — that is the question.", focus: "shakespearean-rhythm", category: "authentic" },
  { id: "au-02", text: "Ask not what your country can do for you.", focus: "jfk-cadence", category: "authentic" },
  { id: "au-03", text: "In the beginning, there was nothing but the quiet shape of an idea.", focus: "narrative-pace", category: "authentic" },
  { id: "au-04", text: "The universe is under no obligation to make sense to you.", focus: "academic-register", category: "authentic" },
  { id: "au-05", text: "Elementary, my dear Watson — the answer was always in plain sight.", focus: "british-rp", category: "authentic" },
  { id: "au-06", text: "Life is what happens while you're busy making other plans.", focus: "conversational", category: "authentic" },
  { id: "au-07", text: "The only way out of this situation is through it.", focus: "short-emphatic", category: "authentic" },
  { id: "au-08", text: "Innovation distinguishes between a leader and a follower.", focus: "business-register", category: "authentic" },
  { id: "au-09", text: "It is a truth universally acknowledged that mornings are difficult.", focus: "austen-cadence", category: "authentic" },
  { id: "au-10", text: "We choose to go to the moon in this decade because it is hard.", focus: "kennedy-prosody", category: "authentic" },
];

export const CATEGORY_LABELS: Record<Phrase["category"], string> = {
  "minimal-pair": "Minimal pair",
  "phoneme-drill": "Phoneme drill",
  "connected-speech": "Connected speech",
  "authentic": "Authentic",
};

let shuffledOrder: Phrase[] | null = null;

/**
 * Returns PHRASES in a shuffled order, stable for the duration of the session
 * (page reloads reshuffle). Prevents users from always seeing the same first
 * phrase on /practice.
 */
export function shuffledPhrases(): Phrase[] {
  if (shuffledOrder) return shuffledOrder;
  const copy = [...PHRASES];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  shuffledOrder = copy;
  return shuffledOrder;
}

/** Reset shuffle order — for tests or explicit "new mix" actions. */
export function reshufflePhrases(): Phrase[] {
  shuffledOrder = null;
  return shuffledPhrases();
}
