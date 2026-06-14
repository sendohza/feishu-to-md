# -*- coding: utf-8 -*-
"""Chrome cookie extractor for Feishu documents."""
import os
import json
import time
import tempfile
import logging

logger = logging.getLogger("feishu_to_md.cookie_fetcher")


def refresh_cookies(env_path):
    """Extract Feishu cookies from Chrome's encrypted cookie database.
    
    Uses cryptography (AESGCM) or win32crypt as fallback to decrypt
    Chrome's cookies database.
    
    Args:
        env_path: Path to .env file to write cookies to.
        
    Returns:
        True if cookies were extracted and saved, False otherwise.
    """
    logger.info("Extracting Feishu cookies from Chrome...")
    
    cookie_paths = [
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Network\Cookies"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cookies"),
    ]
    state_path = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Local State")
    
    if not os.path.exists(state_path):
        logger.error("Chrome Local State file not found at %s", state_path)
        _print_manual_instructions(env_path)
        return False
    
    try:
        import sqlite3
        import shutil
        
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
        
        # Get the encryption key
        ek_b64 = state.get("os_crypt", {}).get("encrypted_key", "")
        if not ek_b64:
            logger.error("No os_crypt.encrypted_key in Local State")
            _print_manual_instructions(env_path)
            return False
        
        import base64
        ek = base64.b64decode(ek_b64)
        
        # Chrome switched from DPAPI to AES-256-GCM in recent versions
        dk = None
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            assert ek[:5] == b"DPAPI"
            import win32crypt
            dk = win32crypt.CryptUnprotectData(ek[5:], None, None, None, 0)[1]
            use_aesgcm = False
        except Exception as e:
            logger.debug("win32crypt failed (%s), trying direct AESGCM", e)
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                # Newer Chrome uses AES-256-GCM directly with a known key prefix
                key_bytes = base64.b64decode(ek_b64)[5:]  # Remove "DPAPI" prefix
                # Chrome's key is actually base64-encoded and needs OS protection
                import win32crypt
                dk = win32crypt.CryptUnprotectData(ek[5:], None, None, None, 0)[1]
                use_aesgcm = True
            except Exception as e2:
                logger.error("Cannot decrypt Chrome key: %s", e2)
                _print_manual_instructions(env_path)
                return False
        
        for cdb in cookie_paths:
            if not os.path.exists(cdb):
                continue
            
            logger.debug("Trying cookie DB: %s", cdb)
            bak = os.path.join(tempfile.gettempdir(), "feishu_ck_bak.db")
            
            try:
                # Create a backup to avoid locking issues
                src = sqlite3.connect(cdb)
                dst = sqlite3.connect(bak)
                src.backup(dst)
                dst.close()
                src.close()
            except Exception:
                try:
                    shutil.copy2(cdb, bak)
                except Exception:
                    logger.warning("Cannot backup cookie DB, proceeding with original")
                    bak = cdb
            
            try:
                conn = sqlite3.connect(bak)
                rows = conn.execute(
                    "SELECT host_key, name, encrypted_value "
                    "FROM cookies "
                    "WHERE host_key LIKE '%feishu%' OR host_key LIKE '%lf.cn%'"
                ).fetchall()
                conn.close()
            except Exception as e:
                logger.warning("Query cookie DB failed: %s", e)
                continue
            
            try:
                os.remove(bak)
            except OSError:
                pass
            
            parts = []
            for host, name, ev in rows:
                if not ev:
                    continue
                try:
                    if use_aesgcm and dk:
                        plain = AESGCM(dk).decrypt(ev[3:15], ev[15:], None)
                        parts.append(f"{name}={plain.decode('utf-8')}")
                    else:
                        plain = win32crypt.CryptUnprotectData(ev, None, None, None, 0)[1]
                        parts.append(f"{name}={plain.decode('utf-8')}")
                except Exception:
                    pass  # Skip undecryptable cookies
            
            if parts:
                ck = "; ".join(parts)
                logger.info("Extracted %d Feishu cookies", len(parts))
                _write_cookies_to_env(env_path, ck)
                return True
        
        logger.warning("No Feishu cookies found in Chrome")
        _print_manual_instructions(env_path)
        return False
        
    except Exception as e:
        logger.error("Cookie extraction error: %s", e, exc_info=True)
        _print_manual_instructions(env_path)
        return False


def _write_cookies_to_env(env_path, cookies):
    """Write cookies to .env file, preserving other content."""
    lines = []
    has = False
    
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("FEISHU_COOKIES="):
                    lines.append(f"FEISHU_COOKIES={cookies}\n")
                    has = True
                else:
                    lines.append(line)
    
    if not has:
        lines.append("\n# Chrome browser cookies (auto-extracted)\n")
    
    lines.append(f"FEISHU_COOKIES={cookies}\n")
    
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    
    logger.info("Saved cookies to %s", env_path)
    print("  Ready! Images will now download automatically.")


def _print_manual_instructions(env_path):
    """Print instructions for manual cookie setup."""
    print("  Could not auto-extract cookies.")
    print("  Manual: Chrome DevTools -> Console -> document.cookie -> copy paste to .env as:")
    print(f'  FEISHU_COOKIES="<paste here>"')
