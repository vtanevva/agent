# Simple keyword-based emotion detection (no heavy ML models needed)
# This replaces the Transformers pipeline that was using 500MB+ of memory

# Comprehensive emotion keywords for mental health context
EMOTION_KEYWORDS = {
    'joy': ['happy', 'excited', 'great', 'wonderful', 'amazing', 'fantastic', 'elated', 'thrilled', 'delighted', 'ecstatic', 'overjoyed', 'blessed', 'grateful', 'content', 'peaceful'],
    'sadness': ['sad', 'depressed', 'down', 'miserable', 'hopeless', 'sorrow', 'grief', 'melancholy', 'blue', 'gloomy', 'heartbroken', 'devastated', 'crushed', 'empty', 'lonely'],
    'anger': ['angry', 'furious', 'mad', 'frustrated', 'annoyed', 'irritated', 'enraged', 'livid', 'outraged', 'fuming', 'seething', 'hostile', 'aggressive', 'bitter', 'resentful'],
    'fear': ['scared', 'afraid', 'worried', 'anxious', 'terrified', 'panicked', 'nervous', 'tense', 'stressed', 'overwhelmed', 'frightened', 'horrified', 'dread', 'paranoid', 'insecure'],
    'surprise': ['shocked', 'surprised', 'astonished', 'amazed', 'stunned', 'bewildered', 'confused', 'perplexed', 'baffled', 'startled', 'taken aback', 'flabbergasted'],
    'disgust': ['disgusted', 'repulsed', 'revolted', 'appalled', 'sickened', 'nauseated', 'offended', 'outraged', 'horrified', 'disturbed', 'uncomfortable'],
    'trust': ['trusting', 'confident', 'secure', 'assured', 'comfortable', 'safe', 'protected', 'supported', 'encouraged', 'hopeful', 'optimistic'],
    'anticipation': ['excited', 'eager', 'enthusiastic', 'motivated', 'inspired', 'determined', 'focused', 'ambitious', 'driven', 'passionate', 'energetic']
}

# Keywords for suicide/self-harm detection - enhanced version
SUICIDE_KEYWORDS = [
    "kill myself", "end it all", "suicidal", "I want to die", "self-harm", "can't go on", "hurt myself",
    "don't want to live", "life isn't worth it", "better off dead", "no reason to live", "end my life",
    "take my life", "commit suicide", "end everything", "give up", "no hope", "hopeless", "worthless",
    "burden", "everyone would be better off", "no one cares", "no one would miss me", "pain will end",
    "escape", "relief", "peace", "rest", "sleep forever", "never wake up", "disappear", "vanish"
]

def detect_emotion(text):
    """
    Simple keyword-based emotion detection
    Returns: (emotion, confidence_score)
    """
    if not text or len(text.strip()) == 0:
        return 'neutral', 0.0
    
    text_lower = text.lower()
    emotion_scores = {}
    
    # Count keyword matches for each emotion
    for emotion, keywords in EMOTION_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in text_lower)
        if score > 0:
            emotion_scores[emotion] = score
    
    if not emotion_scores:
        return 'neutral', 0.5
    
    # Get emotion with highest score
    best_emotion = max(emotion_scores.items(), key=lambda x: x[1])
    
    # Calculate confidence (normalize by text length and keyword count)
    confidence = min(0.9, best_emotion[1] / max(1, len(text.split()) * 0.1))
    
    return best_emotion[0], confidence

def detect_suicidal_intent(text):
    """
    Enhanced suicide/self-harm detection using keywords
    Returns: True if suicidal intent detected, False otherwise
    """
    if not text:
        return False
    
    text_lower = text.lower()
    
    # Check for suicide keywords
    for keyword in SUICIDE_KEYWORDS:
        if keyword in text_lower:
            return True
    
    # Additional context checks
    suicide_indicators = [
        "want to die" in text_lower,
        "end my life" in text_lower,
        "no reason to live" in text_lower,
        "better off dead" in text_lower,
        "life isn't worth it" in text_lower
    ]
    
    return any(suicide_indicators)

def get_emotion_summary(text):
    """
    Get a more detailed emotion analysis
    Returns: dict with emotion breakdown
    """
    if not text:
        return {'primary': 'neutral', 'confidence': 0.0, 'secondary': []}
    
    text_lower = text.lower()
    emotion_scores = {}
    
    for emotion, keywords in EMOTION_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in text_lower)
        if score > 0:
            emotion_scores[emotion] = score
    
    if not emotion_scores:
        return {'primary': 'neutral', 'confidence': 0.5, 'secondary': []}
    
    # Sort emotions by score
    sorted_emotions = sorted(emotion_scores.items(), key=lambda x: x[1], reverse=True)
    
    primary_emotion = sorted_emotions[0]
    secondary_emotions = [emotion for emotion, score in sorted_emotions[1:3] if score > 0]
    
    confidence = min(0.9, primary_emotion[1] / max(1, len(text.split()) * 0.1))
    
    return {
        'primary': primary_emotion[0],
        'confidence': confidence,
        'secondary': secondary_emotions
    }
