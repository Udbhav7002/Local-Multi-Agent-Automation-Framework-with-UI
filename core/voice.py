"""
Voice module for handling local speech-to-text input.
"""
import logging
import speech_recognition as sr
from rich import print

logger = logging.getLogger("Voice")

class VoiceInput:
    """Handles listening to the microphone and transcribing audio."""

    def __init__(self):
        self.recognizer = sr.Recognizer()

    def listen(self, timeout=5, phrase_time_limit=15) -> str:
        """
        Listen to the microphone and return transcribed text.
        """
        try:
            with sr.Microphone() as source:
                # Adjust for ambient noise
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                print("\n  [bold #00ff00]Listening... Speak now.[/bold #00ff00]")
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                
            print("  [#888888]Transcribing...[/#888888]")
            
            try:
                # Try local whisper first
                # requires: pip install openai-whisper
                text = self.recognizer.recognize_whisper(audio, model="base.en").strip()
                logger.debug("Transcribed via Whisper: %s", text)
                return text
            except Exception as e:
                logger.debug("Whisper failed or not installed (%s). Falling back to Google SR.", e)
                # Fallback to Google SR
                text = self.recognizer.recognize_google(audio).strip()
                logger.debug("Transcribed via Google: %s", text)
                return text

        except sr.WaitTimeoutError:
            print("  [#ff0000]Listening timed out. No speech detected.[/#ff0000]")
            return ""
        except sr.UnknownValueError:
            print("  [#ff0000]Could not understand audio.[/#ff0000]")
            return ""
        except sr.RequestError as e:
            print(f"  [#ff0000]Could not request results; {e}[/#ff0000]")
            return ""
        except Exception as e:
            print(f"  [#ff0000]Microphone error: {e}[/#ff0000]")
            return ""
