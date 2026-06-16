import { useRef, useState } from "react";
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import { useAuth } from "../auth";
import { api } from "../api/client";

const RESULT = {
  IDLE: "idle",
  LOADING: "loading",
  IN: "in",
  OUT: "out",
  ERROR: "error",
};

export default function ScannerScreen() {
  const { token, user, logout } = useAuth();
  const [permission, requestPermission] = useCameraPermissions();
  const [state, setState] = useState(RESULT.IDLE);
  const [message, setMessage] = useState("");
  // Guard so a single QR isn't posted dozens of times while in frame.
  const lockRef = useRef(false);

  const handleScanned = async ({ data }) => {
    if (lockRef.current || state === RESULT.LOADING) return;
    lockRef.current = true;
    setState(RESULT.LOADING);
    setMessage("");

    try {
      const res = await api.scan(token, data);
      setState(res.type === "IN" ? RESULT.IN : RESULT.OUT);
      setMessage(res.message);
    } catch (e) {
      setState(RESULT.ERROR);
      setMessage(e.message || "Geçersiz kod");
    }
  };

  const reset = () => {
    setState(RESULT.IDLE);
    setMessage("");
    lockRef.current = false;
  };

  // --- Permission gates ----------------------------------------------------
  if (!permission) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color="#ffc83d" />
      </View>
    );
  }
  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={styles.infoText}>
          QR okutmak için kamera izni gereklidir.
        </Text>
        <TouchableOpacity style={styles.primaryBtn} onPress={requestPermission}>
          <Text style={styles.primaryBtnText}>İzin Ver</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.linkBtn} onPress={logout}>
          <Text style={styles.linkText}>Çıkış Yap</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const showOverlay = state !== RESULT.IDLE;

  return (
    <View style={styles.container}>
      <CameraView
        style={StyleSheet.absoluteFill}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
        onBarcodeScanned={state === RESULT.IDLE ? handleScanned : undefined}
      />

      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerName}>{user?.full_name}</Text>
        <TouchableOpacity onPress={logout}>
          <Text style={styles.linkText}>Çıkış</Text>
        </TouchableOpacity>
      </View>

      {/* Framing guide */}
      {!showOverlay && (
        <View style={styles.guideWrap} pointerEvents="none">
          <View style={styles.guideBox} />
          <Text style={styles.guideText}>
            Tablet ekranındaki QR kodu çerçeveye alın
          </Text>
        </View>
      )}

      {/* Result overlay */}
      {showOverlay && (
        <View style={[styles.overlay, overlayStyle(state)]}>
          {state === RESULT.LOADING ? (
            <ActivityIndicator size="large" color="#fff" />
          ) : (
            <>
              <Text style={styles.overlayIcon}>{resultIcon(state)}</Text>
              <Text style={styles.overlayTitle}>{resultTitle(state)}</Text>
              <Text style={styles.overlayMessage}>{message}</Text>
              <TouchableOpacity style={styles.againBtn} onPress={reset}>
                <Text style={styles.againBtnText}>Tekrar Okut</Text>
              </TouchableOpacity>
            </>
          )}
        </View>
      )}
    </View>
  );
}

function resultIcon(state) {
  if (state === RESULT.IN) return "✓";
  if (state === RESULT.OUT) return "↩";
  return "✕";
}
function resultTitle(state) {
  if (state === RESULT.IN) return "Giriş Başarılı";
  if (state === RESULT.OUT) return "Çıkış Başarılı";
  return "Geçersiz Kod";
}
function overlayStyle(state) {
  if (state === RESULT.IN) return { backgroundColor: "rgba(22,128,67,0.94)" };
  if (state === RESULT.OUT) return { backgroundColor: "rgba(19,80,140,0.94)" };
  if (state === RESULT.ERROR) return { backgroundColor: "rgba(150,30,30,0.94)" };
  return { backgroundColor: "rgba(11,31,58,0.94)" };
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000" },
  center: {
    flex: 1,
    backgroundColor: "#0b1f3a",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
  },
  header: {
    position: "absolute",
    top: 50,
    left: 20,
    right: 20,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    zIndex: 5,
  },
  headerName: { color: "#fff", fontSize: 16, fontWeight: "600" },
  guideWrap: { flex: 1, alignItems: "center", justifyContent: "center" },
  guideBox: {
    width: 240,
    height: 240,
    borderWidth: 3,
    borderColor: "#ffc83d",
    borderRadius: 24,
  },
  guideText: {
    color: "#fff",
    marginTop: 20,
    fontSize: 15,
    textAlign: "center",
    paddingHorizontal: 30,
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
    padding: 28,
  },
  overlayIcon: { fontSize: 80, color: "#fff", marginBottom: 8 },
  overlayTitle: { fontSize: 30, fontWeight: "700", color: "#fff" },
  overlayMessage: {
    fontSize: 17,
    color: "#fff",
    marginTop: 8,
    textAlign: "center",
    opacity: 0.9,
  },
  againBtn: {
    marginTop: 36,
    backgroundColor: "#fff",
    paddingHorizontal: 36,
    paddingVertical: 14,
    borderRadius: 12,
  },
  againBtnText: { color: "#0b1f3a", fontWeight: "700", fontSize: 16 },
  infoText: {
    color: "#fff",
    fontSize: 16,
    textAlign: "center",
    marginBottom: 20,
  },
  primaryBtn: {
    backgroundColor: "#ffc83d",
    paddingHorizontal: 36,
    paddingVertical: 14,
    borderRadius: 12,
  },
  primaryBtnText: { color: "#0b1f3a", fontWeight: "700", fontSize: 16 },
  linkBtn: { marginTop: 16 },
  linkText: { color: "#ffc83d", fontSize: 15, fontWeight: "600" },
});
