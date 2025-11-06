# Blender-And-Godot-tools
a set of blender and godot tools to help me and others with game dev

To Do, Blender:
- ✅ Export 2.4 Update.
- ✅ Export 2.4.1 Update
- ✅ Lod Tool 1.0 Release.
- ❌ Lod Tool 1.0.1 Update
- ✅ Viewport Navigator 1.1 Update.
- ❌ More Tool Ideas.

To Do, Godot:
- ❌ Auto Instancer Plugin (idea)

## ⚠️ Important Notice for Cloud Storage Users

**Versions 2.4+ include critical path fixes for cloud storage and sync environments.**

If you're using versions **1.0 through 2.3** and experience export directory errors (especially with OneDrive, Google Drive, Dropbox, or other cloud storage), here's the workaround:

### Temporary Fix for Older Versions:
1. **Use full absolute paths** from File Explorer instead of relative paths
2. Example: Use `C:\Users\YourName\Documents\Exports\` instead of `//exports\`
3. Or upgrade to **version 2.4+** where this is fixed automatically

### What Was Fixed in 2.4+:
- Proper handling of relative paths (`//`) in cloud-synced folders
- Better compatibility with OneDrive, Google Drive, Dropbox, and other cloud storage
- Automatic path normalization for all export operations in sync environments

### Additional Benefits in 2.4+:
- **More Stable Exports** - Reduced failures from path resolution issues
- **Faster Export Operations** - Optimized directory creation and file handling  
- **Better Cross-Platform Support** - Consistent performance across Windows, Mac, and Linux
