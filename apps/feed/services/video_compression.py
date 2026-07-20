"""
Video compression utilities for the backend.
Uses ffmpeg to compress videos before storing them.
"""
import logging
import subprocess
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class VideoCompressionError(Exception):
    """Raised when video compression fails."""
    pass


class BackendVideoCompressor:
    """Handles video compression using ffmpeg."""
    
    # Compression presets for different quality levels
    PRESETS = {
        'low': {
            'bitrate': '500k',
            'scale': '640:480',
            'preset': 'ultrafast',
        },
        'medium': {
            'bitrate': '1000k',
            'scale': '1280:720',
            'preset': 'fast',
        },
        'high': {
            'bitrate': '2000k',
            'scale': '1920:1080',
            'preset': 'medium',
        },
    }
    
    @staticmethod
    def compress_video(
        input_path: str,
        output_path: str,
        quality: str = 'medium',
        timeout: int = 300,
    ) -> bool:
        """
        Compress a video file using ffmpeg.
        
        Args:
            input_path: Path to the input video file
            output_path: Path to save the compressed video
            quality: Compression quality ('low', 'medium', 'high')
            timeout: Timeout in seconds for the compression process
            
        Returns:
            True if compression was successful, False otherwise
            
        Raises:
            VideoCompressionError: If ffmpeg is not installed or other errors occur
        """
        try:
            # Validate quality preset
            if quality not in BackendVideoCompressor.PRESETS:
                logger.warning(f'Unknown quality preset: {quality}, using medium')
                quality = 'medium'
            
            preset = BackendVideoCompressor.PRESETS[quality]
            
            # Check if input file exists
            if not os.path.exists(input_path):
                raise VideoCompressionError(f'Input file not found: {input_path}')
            
            # Ensure output directory exists
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Build ffmpeg command
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-c:v', 'libx264',
                '-preset', preset['preset'],
                '-b:v', preset['bitrate'],
                '-c:a', 'aac',
                '-b:a', '128k',
                '-vf', f"scale={preset['scale']}:force_original_aspect_ratio=decrease,pad={preset['scale']}:(ow-iw)/2:(oh-ih)/2",
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                '-y',  # Overwrite output file without asking
                output_path,
            ]
            
            logger.info(f'Starting video compression: {input_path} -> {output_path} (quality: {quality})')
            
            # Run ffmpeg
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                logger.error(f'Video compression timed out after {timeout} seconds')
                raise VideoCompressionError(f'Compression timeout after {timeout}s')
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                logger.error(f'FFmpeg error: {error_msg}')
                raise VideoCompressionError(f'FFmpeg failed with code {process.returncode}')
            
            # Verify output file was created
            if not os.path.exists(output_path):
                raise VideoCompressionError('Output file was not created')
            
            # Log compression results
            input_size = os.path.getsize(input_path)
            output_size = os.path.getsize(output_path)
            compression_ratio = ((1 - (output_size / input_size)) * 100) if input_size > 0 else 0
            
            logger.info(
                f'Video compression successful: '
                f'{input_size / 1024 / 1024:.2f}MB -> {output_size / 1024 / 1024:.2f}MB '
                f'({compression_ratio:.1f}% reduction)'
            )
            
            return True
            
        except subprocess.TimeoutExpired:
            raise VideoCompressionError(f'Compression timeout after {timeout}s')
        except FileNotFoundError:
            raise VideoCompressionError('FFmpeg not found. Please install FFmpeg.')
        except Exception as e:
            logger.error(f'Video compression error: {str(e)}')
            raise VideoCompressionError(f'Compression failed: {str(e)}')
    
    @staticmethod
    def get_video_info(video_path: str) -> Optional[dict]:
        """
        Extract video information using ffprobe.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            Dictionary with video information (duration, width, height, bitrate) or None
        """
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration,size,bit_rate:stream=width,height,r_frame_rate',
                '-of', 'default=noprint_wrappers=1:nokey=1:noprint_wrappers=1',
                video_path,
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.warning(f'Could not extract video info: {video_path}')
                return None
            
            # Parse basic info
            lines = result.stdout.strip().split('\n')
            info = {}
            
            if len(lines) >= 1 and lines[0]:
                try:
                    info['duration'] = float(lines[0])
                except (ValueError, IndexError):
                    pass
            
            if len(lines) >= 2 and lines[1]:
                try:
                    info['file_size'] = int(lines[1])
                except (ValueError, IndexError):
                    pass
            
            return info if info else None
            
        except Exception as e:
            logger.warning(f'Error getting video info: {str(e)}')
            return None
