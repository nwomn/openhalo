package dev.openhalo.android.edge

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

data class AndroidDeviceIdentity(
    val alias: String,
    val publicKey: String,
    val publicKeyFingerprint: String
)

/** Android Keystore backed P-256 identity; private key bytes never leave Keystore. */
class AndroidDeviceIdentityStore {
    fun loadOrCreate(deviceId: String): AndroidDeviceIdentity {
        require(deviceId.isNotBlank()) { "deviceId must not be blank" }
        val alias = "openhalo.edge.p256.$deviceId"
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        if (!keyStore.containsAlias(alias)) {
            KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, ANDROID_KEYSTORE)
                .apply {
                    initialize(
                        KeyGenParameterSpec.Builder(
                            alias,
                            KeyProperties.PURPOSE_SIGN
                        )
                            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                            .setDigests(KeyProperties.DIGEST_SHA256)
                            .build()
                    )
                }
                .generateKeyPair()
        }
        val certificate = keyStore.getCertificate(alias)
            ?: error("Android Keystore did not return the device certificate")
        val publicKey = base64Url(certificate.publicKey.encoded)
        return AndroidDeviceIdentity(
            alias = alias,
            publicKey = publicKey,
            publicKeyFingerprint = sha256Fingerprint(certificate.publicKey.encoded)
        )
    }

    fun sign(alias: String, payload: String): String {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        val privateKey = keyStore.getKey(alias, null) as? PrivateKey
            ?: error("Android Keystore device key is unavailable")
        val signature = Signature.getInstance("SHA256withECDSA")
        signature.initSign(privateKey)
        signature.update(payload.toByteArray(Charsets.UTF_8))
        return base64Url(signature.sign())
    }

    fun delete(deviceId: String) {
        val alias = "openhalo.edge.p256.$deviceId"
        KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }.deleteEntry(alias)
    }

    private fun base64Url(value: ByteArray): String =
        Base64.encodeToString(value, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)

    private fun sha256Fingerprint(value: ByteArray): String =
        "sha256:" + java.security.MessageDigest.getInstance("SHA-256")
            .digest(value)
            .joinToString("") { "%02x".format(it) }

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
    }
}
