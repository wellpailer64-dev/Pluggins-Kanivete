"""Monta o APK do KaniCode sem Android Studio nem Gradle (aapt2 + javac + d8 + apksigner) e instala pelo cabo (adb).

  py -3.13 montar.py [--sem-instalar]

SDK em D:/dev/android (cmdline-tools, build-tools 34, android-34, platform-tools). O endereço com a chave vai num
Config.java gerado em build/ (fora do git). Chave de assinatura própria em D:/dev/android/kanicode.jks.
"""
import json, os, shutil, subprocess, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
SDK = r"D:\dev\android"
BT = os.path.join(SDK, "build-tools", "34.0.0")
JAR = os.path.join(SDK, "platforms", "android-34", "android.jar")
ADB = os.path.join(SDK, "platform-tools", "adb.exe")
KS = os.path.join(SDK, "kanicode.jks")
B = os.path.join(AQUI, "build")


def rodar(*a, **k):
    print(">", os.path.basename(a[0]))
    subprocess.run(list(a), check=True, **k)


def endereco():
    dados = os.path.join(os.path.splitdrive(AQUI)[0] + os.sep, "Kanivete", "KaniCode")
    chave = json.load(open(os.path.join(dados, "movel.json"), encoding="utf-8"))["chave"]
    ts = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"
    nome = json.loads(subprocess.run([ts, "status", "--json"], capture_output=True, text=True, timeout=10).stdout)["Self"]["DNSName"].rstrip(".")
    return f"https://{nome}/?chave={chave}"


def main():
    shutil.rmtree(B, ignore_errors=True)
    gen = os.path.join(B, "gen", "com", "pandalab", "kanicode")
    os.makedirs(gen)
    os.makedirs(os.path.join(B, "classes"))
    with open(os.path.join(gen, "Config.java"), "w", encoding="utf-8") as f:
        f.write('package com.pandalab.kanicode;\nfinal class Config { static final String URL = %s; }\n' % json.dumps(endereco()))
    rodar(os.path.join(BT, "aapt2.exe"), "compile", "--dir", os.path.join(AQUI, "res"), "-o", os.path.join(B, "res.zip"))
    rodar(os.path.join(BT, "aapt2.exe"), "link", "-I", JAR, "--manifest", os.path.join(AQUI, "AndroidManifest.xml"),
          "--java", os.path.join(B, "gen"), "-o", os.path.join(B, "base.apk"), os.path.join(B, "res.zip"))
    fontes = [os.path.join(r, n) for d in (os.path.join(AQUI, "src"), os.path.join(B, "gen")) for r, _, ns in os.walk(d) for n in ns if n.endswith(".java")]
    rodar("javac", "-encoding", "UTF-8", "--release", "11", "-classpath", JAR, "-d", os.path.join(B, "classes"), *fontes)
    classes = [os.path.join(r, n) for r, _, ns in os.walk(os.path.join(B, "classes")) for n in ns if n.endswith(".class")]
    rodar(os.path.join(BT, "d8.bat"), "--lib", JAR, "--min-api", "29", "--output", B, *classes, shell=False)
    shutil.copy(os.path.join(B, "base.apk"), os.path.join(B, "sem_assinar.apk"))
    import zipfile
    with zipfile.ZipFile(os.path.join(B, "sem_assinar.apk"), "a") as z:
        z.write(os.path.join(B, "classes.dex"), "classes.dex")
    rodar(os.path.join(BT, "zipalign.exe"), "-f", "4", os.path.join(B, "sem_assinar.apk"), os.path.join(B, "alinhado.apk"))
    if not os.path.isfile(KS):
        rodar("keytool", "-genkeypair", "-keystore", KS, "-alias", "kanicode", "-keyalg", "RSA", "-keysize", "2048",
              "-validity", "10000", "-storepass", "kanicode", "-keypass", "kanicode", "-dname", "CN=Pandalab KaniCode")
    final = os.path.join(AQUI, "KaniCode.apk")
    rodar(os.path.join(BT, "apksigner.bat"), "sign", "--ks", KS, "--ks-pass", "pass:kanicode", "--out", final,
          os.path.join(B, "alinhado.apk"))
    print("APK:", final)
    if "--sem-instalar" not in sys.argv:
        rodar(ADB, "install", "-r", final)


if __name__ == "__main__":
    main()
