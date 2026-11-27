-- « Désinstaller VisionAId » : application livrée dans le .dmg, à côté de VisionAId.
-- Supprime l'application et tout ce qu'elle a écrit (réglages, certificats, journal, modèles).
-- VISIONAID_UNINSTALL_SILENT=1 : sans dialogue (test automatique).

set silent to (system attribute "VISIONAID_UNINSTALL_SILENT") is "1"
set homeDir to POSIX path of (path to home folder)
set bundleId to "fr.visionaid.app"

if not silent then
	display dialog "Désinstaller VisionAId ?" & return & return & ¬
		"L'application, ses réglages et les modèles téléchargés (environ 3 Go) seront supprimés." ¬
		buttons {"Annuler", "Désinstaller"} default button "Annuler" cancel button "Annuler" ¬
		with title "VisionAId" with icon caution
end if

-- fermer VisionAId s'il est ouvert (et ses processus de guidage)
do shell script "pkill -x VisionAId; sleep 1; pkill -9 -x VisionAId; exit 0"

set appPaths to {"/Applications/VisionAId.app", homeDir & "Applications/VisionAId.app"}
set dataPaths to {homeDir & "Library/Application Support/VisionAId", ¬
	homeDir & "Library/Caches/" & bundleId, ¬
	homeDir & "Library/WebKit/" & bundleId, ¬
	homeDir & "Library/HTTPStorages/" & bundleId, ¬
	homeDir & "Library/Preferences/" & bundleId & ".plist", ¬
	homeDir & "Library/Saved Application State/" & bundleId & ".savedState"}

set targets to ""
repeat with p in (appPaths & dataPaths)
	set targets to targets & " " & quoted form of (p as text)
end repeat

try
	do shell script "rm -rf" & targets
on error
	-- application installée par un autre compte : mot de passe administrateur demandé
	do shell script "rm -rf" & targets with administrator privileges
end try

if not silent then
	display dialog "VisionAId a été désinstallé." buttons {"OK"} default button "OK" ¬
		with title "VisionAId" with icon note
end if
