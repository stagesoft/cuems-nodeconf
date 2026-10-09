# Deployment Steps for Network Map Bug Fix

## Summary
Fixed the `'NoneType' object has no attribute 'tag'` error when writing network_map.xml.

## Changes Made
1. Fixed missing `mac` field in `CuemsAvahiListener.update_service()`
2. Added validation in `write_network_map()` to catch None values with clear error messages
3. Added normalization in `read_network_map()` to handle legacy data formats
4. Restored authoritative XSD from cuems-utils (DO NOT modify locally)
5. Used `strtobool` from cuemsutils.helpers for consistent boolean parsing

## Deployment Steps

```bash
# 1. Build the updated package
cd /path/to/cuems-nodeconf
debuild -b -uc -us -nc

# 2. Install the new package
sudo dpkg -i ../cuems-nodeconf_*.deb

# 3. Restart the service
sudo systemctl restart cuems-nodeconf

# 4. Check the service status
sudo systemctl status cuems-nodeconf

# 5. Monitor logs for errors
sudo journalctl -u cuems-nodeconf -f
```

## Verification

After deployment, verify:

1. **Service starts without errors:**
```bash
sudo systemctl status cuems-nodeconf
```

2. **Network map uses correct format:**
```bash
sudo cat /etc/cuems/network_map.xml
# Should contain <node_list> and <node> tags (from authoritative XSD)
```

3. **No 'NoneType' errors in logs:**
```bash
sudo journalctl -u cuems-nodeconf --since "5 minutes ago" | grep -i "nonetype\|error"
```

4. **Node adoption/unadoption works:**
- Test through your application's node management interface
- Verify adopted nodes persist across service restarts

## Important Notes

### XSD Management
- **CRITICAL**: `network_map.xsd` is authoritative in cuems-utils
- This project copies the XSD from: `/casas/dion/src/cuems/cuems-utils/src/cuemsutils/xml/schemas/network_map.xsd`
- **Never modify the XSD locally** - changes must be made in cuems-utils
- The XSD is shared across the entire CUEMS system

### Boolean Handling
- Uses `strtobool` from `cuemsutils.helpers` (standard across CUEMS)
- Handles: 'True'/'False', 'true'/'false', 'yes'/'no', '1'/'0', etc.
- Consistent with rest of CUEMS system

### Backward Compatibility
- Handles old XML files with `NodeType.master` format
- New writes use clean format: just `master` (not `NodeType.master`)
- Existing network_map.xml files will be read correctly

## Testing

All 58 unit tests pass:
```bash
cd /path/to/cuems-nodeconf
python -m pytest tests/ -v
```

## Rollback Procedure

If issues occur:

```bash
# Reinstall previous package version
sudo dpkg -i /path/to/previous/cuems-nodeconf_*.deb

# Restart service
sudo systemctl restart cuems-nodeconf

# Verify
sudo systemctl status cuems-nodeconf
```

## Support

If issues persist after deployment:
1. Check logs for detailed error messages (now includes which node/field is None)
2. Verify `/etc/cuems/network_map.xsd` matches cuems-utils version
3. Examine `/etc/cuems/network_map.xml` structure
4. Check that all Python files were updated correctly in the package
